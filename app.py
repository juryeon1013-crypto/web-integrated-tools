from flask import Flask, render_template, request, jsonify, send_file, session, flash, redirect, url_for
from flask_session import Session
from werkzeug.exceptions import RequestEntityTooLarge
import os
from datetime import datetime
import pytz
import sqlite3
from werkzeug.utils import secure_filename
import logging
import traceback
# from config import Config
from werkzeug.serving import WSGIRequestHandler

# Werkzeug 크기 제한 완전 제거
import werkzeug
werkzeug.formparser.MAX_CONTENT_LENGTH = None

# 변환 모듈들 import
from modules.domeggook_converter import DomeggookConverter
from modules.hauser_converter import HauserConverter  # 하우저 변환기 활성화
from modules.naverpay_converter import NaverpayConverter  # 네이버페이 변환기 활성화

app = Flask(__name__)
app.secret_key = 'dev-secret-key-change-in-production'

# 필요한 폴더 생성 (앱 시작 시 항상 실행)
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)

# 로깅 설정
def setup_logging():
    """로깅 시스템 설정"""
    # 로그 폴더 생성
    log_folder = 'logs'
    os.makedirs(log_folder, exist_ok=True)
    
    # 로그 포맷 설정
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 파일 핸들러 설정
    file_handler = logging.FileHandler(os.path.join(log_folder, 'app.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # 에러 로그 핸들러 설정
    error_handler = logging.FileHandler(os.path.join(log_folder, 'error.log'), encoding='utf-8')
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(log_format))
    
    # 앱 로거 설정
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_handler)
    
    # Werkzeug 로거 설정 (Flask 내부 로그)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.WARNING)
    werkzeug_logger.addHandler(file_handler)

# 로깅 시스템 초기화
setup_logging()

# 세션을 서버 사이드에 저장 (쿠키 크기 제한 해결)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './session_data'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'naverpay:'

# Flask-Session 초기화
Session(app)

# 모든 크기 제한 완전 제거 (Request Entity Too Large 오류 해결)
app.config['MAX_CONTENT_LENGTH'] = None  # 완전 제거
WSGIRequestHandler.max_content_length = None

# 추가 크기 제한 해제 설정
import werkzeug
werkzeug.formparser.MAX_CONTENT_LENGTH = None

# Flask 내부 제한도 완전 해제
app.config['MAX_CONTENT_LENGTH'] = None

# 폼 파서 메모리 한도(기본 500KB)를 충분히 키워주세요 (예: 10MB)
app.config["MAX_FORM_MEMORY_SIZE"] = 10 * 1024 * 1024  # 10MB
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024     # 10MB

# 413 오류 핸들러 추가
@app.errorhandler(RequestEntityTooLarge)
def handle_413(e):
    return jsonify({
        "error": "Request too large",
        "MAX_FORM_MEMORY_SIZE": app.config.get("MAX_FORM_MEMORY_SIZE"),
        "MAX_CONTENT_LENGTH": app.config.get("MAX_CONTENT_LENGTH"),
        "hint": "폼 파서 한도를 늘리거나 JSON 전송으로 변경하세요."
    }), 413

# 기본 설정 (config.py 없이 직접 설정)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
app.config['DATABASE'] = 'database.db'
app.config['LOG_FOLDER'] = 'logs'
# ALLOWED_EXTENSIONS 설정 추가 (파일 확장자 검증용)
app.config['ALLOWED_EXTENSIONS'] = {
    'html': ['.html', '.htm'],
    'text': ['.txt'],
    'excel': ['.xlsx', '.xls']
}

try:
    app.jinja_env.auto_reload = True
except Exception:
    pass

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            input_filename TEXT,
            output_filename TEXT,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 입력값 저장 테이블 추가
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_inputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_type TEXT NOT NULL,
            input_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# 입력값 저장 함수
def save_input_data(tool_type, input_data):
    """입력값을 데이터베이스에 저장 (24시간 보관)"""
    try:
        print(f"[저장] 시작: {tool_type}, 상품명: {input_data.get('product_title', 'Unknown')}")
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 입력 데이터를 JSON으로 저장
        import json
        json_data = json.dumps(input_data, ensure_ascii=False)
        
        # 한국시간으로 명시적으로 저장
        korean_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT INTO saved_inputs (tool_type, input_data, created_at)
            VALUES (?, ?, ?)
        ''', (tool_type, json_data, korean_time))
        
        conn.commit()
        conn.close()
        
        print(f"[저장] 완료: {tool_type}")
        
        # 24시간 이상 된 데이터 삭제
        cleanup_old_inputs()
        
        return True
    except Exception as e:
        print(f"[저장] 오류: {str(e)}")
        return False

# 입력값 불러오기 함수
def get_saved_inputs(tool_type):
    """저장된 입력값들을 불러오기 (당일만)"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 당일 데이터만 조회
        cursor.execute('''
            SELECT id, input_data, created_at
            FROM saved_inputs 
            WHERE tool_type = ? 
            AND DATE(created_at) = DATE('now')
            ORDER BY created_at DESC
        ''', (tool_type,))
        
        results = cursor.fetchall()
        conn.close()
        
        # JSON 데이터를 파이썬 객체로 변환
        import json
        saved_inputs = []
        for row in results:
            try:
                input_data = json.loads(row[1])
                saved_inputs.append({
                    'id': row[0],
                    'data': input_data,
                    'created_at': row[2]
                })
            except:
                continue
                
        return saved_inputs
    except Exception as e:
        print(f"입력값 불러오기 오류: {str(e)}")
        return []

# 오래된 입력값 정리 함수
def cleanup_old_inputs():
    """24시간 이상 된 입력값 삭제"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM saved_inputs 
            WHERE created_at < datetime('now', '-1 day')
        ''')
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"오래된 입력값 정리 오류: {str(e)}")
        return False

# 허용된 파일 확장자 확인
def allowed_file(filename, file_type):
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in [ext.replace('.', '') for ext in app.config['ALLOWED_EXTENSIONS'].get(file_type, [])]

# 작업 히스토리 저장
def save_job_history(tool_type, description, metadata=None):
    """작업 히스토리를 데이터베이스에 저장"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 세션 ID 생성 (간단한 UUID 대신 타임스탬프 사용)
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 메타데이터를 문자열로 변환하여 저장 (오류 방지)
        metadata_str = str(metadata) if metadata else None
        
        cursor.execute('''
            INSERT INTO jobs (session_id, tool_type, input_filename, output_filename, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, tool_type, description, metadata_str, 'completed'))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"작업 히스토리 저장 오류: {e}")

# 변환기 인스턴스 생성
domeggook_converter = DomeggookConverter()
hauser_converter = HauserConverter()  # 하우저 변환기 활성화
naverpay_converter = NaverpayConverter()  # 네이버페이 변환기 활성화

# 카드영수증 생성 함수
def handle_card_receipt_generation():
    """카드영수증 생성 요청 처리"""
    try:
        # 주문 정보 수집
        order_data = {
            'order_number': request.form.get('order_number', '0202'),
            'product_title': request.form.get('product_title', '아르코에어'),
            'supplier_name': request.form.get('supplier_name', '아르코에어'),
            'supplier_email': request.form.get('supplier_email', '아르코에어'),
            'supplier_phone': request.form.get('supplier_phone', '010-0000-1234'),
            'quantity': request.form.get('quantity', '10'),
            'payment_amount': request.form.get('payment_amount', '200000'),
            'recipient_name': request.form.get('recipient_name', '아르코에어'),
            'address': request.form.get('address', '아르코에어'),
            'phone': request.form.get('phone', '01080809090'),
            'order_date': request.form.get('order_date', '20250602'),
            # 카드영수증에 필요한 추가 정보
            'store_name': request.form.get('store_name', '아르코에어'),
            'business_number': request.form.get('business_number', '1234567890'),
            'ceo_name': request.form.get('ceo_name', '아르코에어'),
            'supplier_address': request.form.get('supplier_address', '아르코에어'),
            'supplier_contact': request.form.get('supplier_contact', '010-0000-1234'),
            # JavaScript에서 전송한 자동 계산된 값들
            'card_order_number': request.form.get('card_order_number', ''),
            'transaction_time': request.form.get('transaction_time', ''),
            'approval_number': request.form.get('approval_number', ''),
            'product_info': request.form.get('product_info', ''),
            'supply_amount': request.form.get('supply_amount', ''),
            'vat_amount': request.form.get('vat_amount', ''),
            'tax_free_amount': request.form.get('tax_free_amount', ''),
            'total_amount': request.form.get('total_amount', '')
        }
        
        # 카드영수증 생성
        card_receipt = domeggook_converter.create_card_receipt(order_data)
        
        if card_receipt and not card_receipt.startswith("카드영수증 생성 중 오류가 발생했습니다"):
            # 카드영수증 파일 저장
            saved_filename = None
            try:
                # downloads 폴더가 없으면 생성
                os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
                
                # 파일명 생성 (네이버페이와 동일한 형식)
                today = datetime.now().strftime('%y%m%d')
                product_title = order_data.get('product_title', '아르코에어')
                
                # 파일명 형식: 날짜_상품명_카드영수증.txt
                filename = f"{today}_{product_title}_카드영수증.txt"
                # 파일명 안전성 검사
                safe_filename = domeggook_converter.sanitize_filename(filename) if hasattr(domeggook_converter, 'sanitize_filename') else filename
                
                filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], safe_filename)
                
                # 파일 저장
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(card_receipt)
                
                saved_filename = safe_filename
                print(f"카드영수증 파일 저장 완료: {filepath}")
                
            except Exception as save_error:
                print(f"카드영수증 파일 저장 오류: {str(save_error)}")
            
            return jsonify({
                'success': True,
                'card_receipt': card_receipt,
                'download_file': saved_filename
            })
        else:
            return jsonify({
                'success': False,
                'error': card_receipt or '카드영수증 생성에 실패했습니다.'
            })
            
    except Exception as e:
        print(f"카드영수증 생성 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'카드영수증 생성 중 오류가 발생했습니다: {str(e)}'
        })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/healthz')
def healthz():
    # 헬스체크 엔드포인트 (브라우저/스크립트에서 200 응답 확인용)
    return 'ok', 200

@app.route('/domeggook', methods=['GET', 'POST'])
def domeggook():
    if request.method == 'POST':
        # 카드영수증 생성 요청인지 확인
        action = request.form.get('action', '')
        if action == 'generate_card_receipt':
            return handle_card_receipt_generation()
        
        try:
            # HTML 내용 가져오기
            html_content = request.form.get('html_content', '')
            if not html_content:
                flash('HTML 내용을 입력해주세요.', 'error')
                return render_template('domeggook.html', result=None)
            
            # 기본 주문 정보 수집
            order_data = {
                'option_count': int(request.form.get('option_count', 5)),
                'order_number': request.form.get('order_number', '0202'),
                'product_title': request.form.get('product_title', '아르코에어'),
                'supplier_name': request.form.get('supplier_name', '아르코에어'),
                'supplier_email': request.form.get('supplier_email', '아르코에어'),
                'supplier_phone': request.form.get('supplier_phone', '010-0000-1234'),
                'quantity': request.form.get('quantity', '10'),
                'payment_amount': request.form.get('payment_amount', '200000'),
                'recipient_name': request.form.get('recipient_name', '아르코에어'),
                'address': request.form.get('address', '아르코에어'),
                'phone': request.form.get('phone', '01080809090'),
                'order_date': request.form.get('order_date', '20250602')
            }
            
            # 옵션 정보 수집
            for i in range(1, order_data['option_count'] + 1):
                order_data[f'option_{i}_name'] = request.form.get(f'option_{i}_name', f'여성용/옐로우')
                order_data[f'option_{i}_quantity'] = request.form.get(f'option_{i}_quantity', '1')
                order_data[f'option_{i}_price'] = request.form.get(f'option_{i}_price', '2550')
            
            # 변환 실행
            result = domeggook_converter.modify_order(html_content, order_data)
            
            # 입력값 저장 (변환 성공 시)
            if result and not result.startswith("HTML 수정 중 오류가 발생했습니다"):
                print(f"[도매꾹] 저장 시도: {order_data.get('product_title', 'Unknown')}")
                save_result = save_input_data('domeggook', order_data)
                print(f"[도매꾹] 저장 결과: {save_result}")
            
            # 파일 저장 기능 추가
            saved_filename = None
            if result and not result.startswith("HTML 수정 중 오류가 발생했습니다"):
                try:
                    # downloads 폴더가 없으면 생성 (파일 저장 오류 방지)
                    os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
                    
                    # 파일명 생성 (네이버페이와 동일한 형식)
                    today = datetime.now().strftime('%y%m%d')
                    product_title = order_data.get('product_title', '아르코에어')
                    
                    # 파일명 형식: 날짜_상품명_주문내역.txt
                    filename = f"{today}_{product_title}_주문내역.txt"
                    # 파일명 안전성 검사
                    safe_filename = domeggook_converter.sanitize_filename(filename) if hasattr(domeggook_converter, 'sanitize_filename') else filename
                    
                    filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], safe_filename)
                    
                    # 파일 저장
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(result)
                    
                    saved_filename = safe_filename
                    print(f"파일 저장 완료: {filepath}")  # 서버 로그에 저장 확인
                    
                except Exception as save_error:
                    print(f"파일 저장 오류: {str(save_error)}")  # 서버 로그에 오류 출력
                    flash(f'변환은 완료되었지만 파일 저장 중 오류가 발생했습니다: {str(save_error)}', 'warning')
            
            # 작업 히스토리 저장
            save_job_history('domeggook', '주문내역 수정', {
                'product_title': order_data['product_title'],
                'option_count': order_data['option_count'],
                'payment_amount': order_data['payment_amount'],
                'saved_filename': saved_filename
            })
            
            flash('주문내역 수정이 완료되었습니다!', 'success')
            return render_template('domeggook.html', result=result, download_file=saved_filename)
            
        except Exception as e:
            print(f"도매꾹 변환 오류: {str(e)}")  # 서버 로그에 오류 출력
            flash(f'오류가 발생했습니다: {str(e)}', 'error')
            # 기본 템플릿 다시 로드
            default_template = domeggook_converter.get_default_template()
            return render_template('domeggook.html', result=None, default_template=default_template)
    
    # GET 요청 시 기본 템플릿 로드
    default_template = domeggook_converter.get_default_template()
    return render_template('domeggook.html', result=None, default_template=default_template)

@app.route('/hauser', methods=['GET', 'POST'])
def hauser():
    if request.method == 'POST':
        try:
            print(f"POST 요청 받음")
            print(f"request.files: {list(request.files.keys())}")
            print(f"request.form: {dict(request.form)}")
            
            # 파일 업로드 확인
            if 'excel_file' not in request.files:
                print("excel_file이 request.files에 없음")
                flash('엑셀 파일을 선택해주세요.', 'error')
                return render_template('hauser.html', result=None)
            
            file = request.files['excel_file']
            print(f"파일명: {file.filename}")
            
            if file.filename == '':
                print("파일명이 비어있음")
                flash('파일을 선택해주세요.', 'error')
                return render_template('hauser.html', result=None)
            
            # 파일 확장자 확인
            if not allowed_file(file.filename, 'excel'):
                print(f"파일 확장자 검증 실패: {file.filename}")
                flash('엑셀 파일(.xlsx, .xls)만 업로드 가능합니다.', 'error')
                return render_template('hauser.html', result=None)
            
            print("파일 검증 통과, 변환 시작")
            
            # 파일 저장
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            print(f"파일 저장 완료: {filepath}")
            
            # 하우저 변환 실행 (원본 파일 직접 수정)
            result = hauser_converter.convert_excel_file(filepath)
            print(f"변환 결과: {result}")
            
            if result.get('success'):
                # 변환된 파일을 downloads 폴더로 복사
                timestamp = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y%m%d_%H%M%S')
                result_filename = f'howser_result_{timestamp}.xlsx'
                result_filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], result_filename)
                
                # downloads 폴더가 없으면 생성
                os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
                
                # 변환된 파일을 downloads 폴더로 복사
                import shutil
                shutil.copy2(filepath, result_filepath)
                
                # 작업 히스토리 저장
                save_job_history('hauser', '엑셀 파일 변환', {
                    'input_file': filename,
                    'output_file': result_filename,
                    'message': result.get('message', '변환 완료')
                })
                
                flash('하우저 변환이 완료되었습니다!', 'success')
                return render_template('hauser.html', result={
                    'filename': result_filename,
                    'message': result.get('message', '변환 완료')
                })
            else:
                flash(f'변환 중 오류가 발생했습니다: {result.get("error", "알 수 없는 오류")}', 'error')
                return render_template('hauser.html', result=None)
                
        except Exception as e:
            print(f"하우저 변환 오류: {str(e)}")
            flash(f'변환 중 오류가 발생했습니다: {str(e)}', 'error')
            return render_template('hauser.html', result=None)
    
    # GET 요청 시 기본 템플릿 로드
    return render_template('hauser.html', result=None)

@app.route('/naverpay')
def naverpay():
    """네이버페이 변환기 메인 페이지"""
    return render_template('naverpay.html', order_result=None, card_result=None, card_data=None)

@app.route('/naverpay/convert', methods=['POST'])
def convert_order():
    """주문내역 변환 - 기존 multi_option_retry.py의 on_replace + ask_and_replace_fields 로직"""
    try:
        print("=== 주문내역 변환 디버깅 시작 ===")
        
        # 디버깅: 주문내역 변환 요청 데이터 로깅
        print(f"request.form keys: {list(request.form.keys())}")
        
        # HTML 내용 가져오기
        html_content = request.form.get('html_content', '')
        if not html_content:
            print("오류: HTML 내용이 없음")
            flash('HTML 내용을 입력해주세요.', 'error')
            return render_template('naverpay.html', order_result=None, card_result=None, card_data=None)
        
        # 옵션 개수 가져오기
        option_count = int(request.form.get('option_count', 5))
        
        # 구매확정일은 HTML에서 자동으로 추출 (사용자 입력 받지 않음)
        purchase_date = None
        
        # 1단계: 주문내역 HTML 처리 (기존 on_replace 로직)
        final_html, trimmed_ul = naverpay_converter.process_order_html(html_content, option_count, purchase_date)
        
        # 2단계: 옵션별 입력 필드 수집 (기존 ask_and_replace_fields 로직)
        option_inputs = []
        for i in range(option_count):
            option = {
                '상품명': request.form.get(f'option_{i}_상품명', ''),
                '옵션명': request.form.get(f'option_{i}_옵션명', ''),
                '수량': request.form.get(f'option_{i}_수량(숫자만)', ''),
                '상품가격': request.form.get(f'option_{i}_상품가격(숫자만)', ''),
                '상품이미지': request.form.get(f'option_{i}_상품이미지', ''),
                '상품 할인 전 금액': request.form.get(f'option_{i}_상품 할인 전 금액(숫자만, 0입력시 미출력)', '')
            }
            option_inputs.append(option)
        
        # 기타 항목 수집
        기타필드 = [
            "스토어명", "배송비", "수령자명", "연락처", "주소",
            "주문금액(총결제금액, 숫자만)", "상품금액(숫자만)", 
            "쿠폰할인(숫자만, 0입력시 div삭제)", "결제배송비(숫자만)", "카드결제금액(숫자만)"
        ]
        기타항목 = {field: request.form.get(field, '') for field in 기타필드}
        
        # 3단계: 필드 적용 (기존 ask_and_replace_fields의 on_ok 로직)
        result = naverpay_converter.apply_order_fields(final_html, trimmed_ul, option_inputs, 기타항목)
        
        # 입력값 저장 (변환 성공 시)
        if result:
            input_data = {
                'html_content': html_content,
                'option_count': option_count,
                'option_inputs': option_inputs,
                '기타항목': 기타항목
            }
            save_input_data('naverpay', input_data)
        
        # 4단계: 카드영수증용 데이터 저장 (기존 로직)
        try:
            임시저장 = {
                "product": option_inputs[0]['상품명'] if option_inputs else '',
                "approval_amount": 기타항목['주문금액(총결제금액, 숫자만)'],
                "total": 기타항목['주문금액(총결제금액, 숫자만)']
            }
            with open("last_order_info.json", "w", encoding="utf-8") as f:
                json.dump(임시저장, f, ensure_ascii=False)
        except Exception as e:
            pass  # 임시저장 실패해도 무시
        
        # 5단계: 파일 저장
        saved_filename = None
        try:
            os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
            # 날짜 형식을 250917 형식으로 설정
            today = datetime.now().strftime('%y%m%d')
            # 상품명은 사용자가 입력한 값 그대로 사용
            first_product = option_inputs[0]['상품명'] if option_inputs else '상품'
            # 파일명 형식: 날짜_상품명_주문내역.txt
            filename = f"{today}_{first_product}_주문내역.txt"
            # 파일명 안전성 검사
            safe_filename = naverpay_converter.sanitize_filename(filename)
            
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], safe_filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(result)
            
            saved_filename = safe_filename
            print(f"주문내역 파일 저장 완료: {filepath}")
            
        except Exception as save_error:
            print(f"파일 저장 오류: {str(save_error)}")
            flash(f'변환은 완료되었지만 파일 저장 중 오류가 발생했습니다: {str(save_error)}', 'warning')
        
        # 작업 히스토리 저장
        save_job_history('naverpay_order', '주문내역 변환', {
            'option_count': option_count,
            'purchase_date': purchase_date,
            'saved_filename': saved_filename
        })
        
        # 주문내역 데이터를 세션에 저장 (카드영수증 변환 시 재사용용)
        print("=== 1단계: 세션 저장 전 데이터 확인 ===")
        print(f"저장할 html_content 길이: {len(html_content)}")
        print(f"저장할 option_count: {option_count}")
        print(f"저장할 option_inputs: {option_inputs}")
        
        session['order_data'] = {
            'html_content': html_content,
            'option_count': option_count,
            'option_inputs': option_inputs,
            '기타항목': 기타항목,
            'order_result': result
        }
        session.modified = True  # 세션 변경사항 강제 저장
        
        print("=== 1단계: 세션 저장 후 확인 ===")
        print(f"세션에 저장된 데이터: {session.get('order_data', '없음')}")
        print(f"세션 전체 키들: {list(session.keys())}")
        print(f"주문내역 데이터 세션 저장 완료: option_count={option_count}, option_inputs 개수={len(option_inputs)}")
        
        flash('주문내역 변환이 완료되었습니다!', 'success')
        
        # 디버깅: 주문내역 변환 완료 시 템플릿 렌더링 데이터 로깅
        print("=== 주문내역 변환 완료 시 템플릿 렌더링 데이터 ===")
        print(f"html_content 길이: {len(html_content) if html_content else 0}")
        print(f"option_count: {option_count}")
        print(f"option_inputs 개수: {len(option_inputs)}")
        print(f"기타항목 개수: {len(기타항목)}")
        print(f"result 길이: {len(result) if result else 0}")
        
        
        return render_template('naverpay.html', 
                             order_result=result, 
                             card_result=None, 
                             card_data=None,
                             active_tab='order',
                             # 입력값들 유지
                             html_content=html_content,
                             option_count=option_count,
                             option_inputs=option_inputs,
                             기타항목=기타항목)
        
    except Exception as e:
        print(f"주문내역 변환 오류: {str(e)}")
        print(f"오류 발생 시점의 request.form: {dict(request.form)}")
        flash(f'주문내역 변환 중 오류가 발생했습니다: {str(e)}', 'error')
        
        # 디버깅: 예외 발생 시에도 기본 데이터로 템플릿 렌더링
        return render_template('naverpay.html', order_result=None, card_result=None, card_data=None, active_tab='order')

@app.route('/naverpay/card', methods=['POST'])
def convert_card():
    """카드영수증 변환 - 기존 multi_option_retry.py의 save_card_receipt 로직"""
    try:
        print("=== 카드영수증 변환 디버깅 시작 ===")
        
        # 디버깅: 요청 데이터 로깅
        print(f"request.form keys: {list(request.form.keys())}")
        print(f"request.form values: {dict(request.form)}")
        
        # 카드영수증 HTML 내용 가져오기
        card_html_content = request.form.get('card_html_content', '')
        if not card_html_content:
            print("오류: 카드영수증 HTML 내용이 없음")
            flash('카드영수증 HTML 내용을 입력해주세요.', 'error')
            return render_template('naverpay.html', order_result=None, card_result=None, card_data=None, active_tab='card')
        
        # 주문내역 관련 데이터도 수집 (입력값 유지용)
        # 세션에서 주문내역 데이터 가져오기 (폼 데이터 대신)
        print("=== 2단계: 세션 가져오기 전 확인 ===")
        print(f"세션 전체 키들: {list(session.keys())}")
        print(f"order_data 키 존재 여부: {'order_data' in session}")
        
        order_data = session.get('order_data', {})
        print(f"가져온 order_data: {order_data}")
        
        html_content = order_data.get('html_content', '')
        option_count = order_data.get('option_count', 5)
        option_inputs = order_data.get('option_inputs', [])
        기타항목 = order_data.get('기타항목', {})
        
        print("=== 2단계: 세션 가져오기 후 확인 ===")
        print(f"가져온 html_content 길이: {len(html_content) if html_content else 0}")
        print(f"가져온 option_count: {option_count}")
        print(f"가져온 option_inputs 개수: {len(option_inputs)}")
        print(f"가져온 기타항목 개수: {len(기타항목)}")
        print(f"가져온 option_inputs 전체: {option_inputs}")
        
        
        # 카드영수증 필드 수집
        card_fields = {
            "product": request.form.get('product', ''),
            "seller": request.form.get('seller', ''),
            "ceo": request.form.get('ceo', ''),
            "biznum": request.form.get('biznum', ''),
            "phone": request.form.get('phone', ''),
            "address": request.form.get('address', ''),
            "approval_amount": request.form.get('approval_amount', ''),
            "supply_amount": request.form.get('supply_amount', ''),
            "tax_amount": request.form.get('tax_amount', ''),
            "service_fee": request.form.get('service_fee', '0'),
            "total": request.form.get('total', '')
        }
        
        # 카드영수증 HTML 처리 (기존 save_card_receipt 로직)
        result = naverpay_converter.process_card_html(card_html_content, card_fields)
        
        # 파일 저장
        saved_filename = None
        try:
            os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
            # 날짜 형식을 250917 형식으로 설정
            today = datetime.now().strftime('%y%m%d')
            # 상품명은 사용자가 입력한 값 그대로 사용
            product = card_fields["product"] or "상품"
            # 파일명 형식: 날짜_상품명_카드영수증.txt
            filename = f"{today}_{product}_카드영수증.txt"
            # 파일명 안전성 검사
            safe_filename = naverpay_converter.sanitize_filename(filename)
            
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], safe_filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(result)
            
            saved_filename = safe_filename
            print(f"카드영수증 파일 저장 완료: {filepath}")
            
        except Exception as save_error:
            print(f"파일 저장 오류: {str(save_error)}")
            flash(f'변환은 완료되었지만 파일 저장 중 오류가 발생했습니다: {str(save_error)}', 'warning')
        
        # 작업 히스토리 저장
        save_job_history('naverpay_card', '카드영수증 변환', {
            'product': card_fields["product"],
            'approval_amount': card_fields["approval_amount"],
            'saved_filename': saved_filename
        })
        
        flash('카드영수증 변환이 완료되었습니다!', 'success')
        
        # 디버깅: 템플릿에 전달할 데이터 로깅
        print("=== 템플릿 렌더링 데이터 ===")
        print(f"html_content 길이: {len(html_content) if html_content else 0}")
        print(f"option_count: {option_count}")
        print(f"option_inputs 개수: {len(option_inputs)}")
        print(f"기타항목 개수: {len(기타항목)}")
        print(f"card_fields: {card_fields}")
        
        
        # 카드영수증 변환 후 주문내역 탭으로 이동할 때 주문 결과도 유지
        order_result = None
        
        if html_content and option_inputs and 기타항목:
            print(f"주문내역 결과 재생성 시도 - html_content: {len(html_content) if html_content else 0}자")
            print(f"주문내역 결과 재생성 시도 - option_inputs: {len(option_inputs) if option_inputs else 0}개")
            print(f"주문내역 결과 재생성 시도 - 기타항목: {len(기타항목) if 기타항목 else 0}개")
            try:
                # 주문내역 변환 로직 실행 (결과만 생성, 파일 저장은 하지 않음)
                import re
                purchase_date = None
                for line in html_content.splitlines():
                    if "구매확정일" in line:
                        text = re.sub('<[^<]+?>', '', line)
                        m = re.search(r'구매확정일\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\([^)]+\)', text)
                        if m:
                            purchase_date = m.group()
                            break
                
                if purchase_date:
                    # 1단계: 주문내역 HTML 처리
                    final_html, trimmed_ul = naverpay_converter.process_order_html(html_content, option_count, purchase_date)
                    # 2단계: 필드 적용
                    order_result = naverpay_converter.apply_order_fields(final_html, trimmed_ul, option_inputs, 기타항목)
                    print(f"주문내역 결과 재생성 완료 (길이: {len(order_result) if order_result else 0}자)")
                    print(f"재생성 시 사용된 option_inputs: {option_inputs}")
                else:
                    print("구매확정일을 찾을 수 없어서 주문내역 결과 재생성 건너뜀")
            except Exception as e:
                print(f"주문내역 결과 재생성 실패: {str(e)}")
                print(f"재생성 실패 시 option_inputs: {option_inputs}")
        else:
            print("주문내역 결과 재생성 조건 미충족")
        
        return render_template('naverpay.html', 
                             order_result=order_result,  # 주문 결과 유지
                             card_result=result, 
                             card_data=card_fields,
                             active_tab='card',
                             card_html_content=card_html_content,
                             # 주문내역 입력값들 유지
                             html_content=html_content,
                             option_count=option_count,
                             option_inputs=option_inputs,
                             기타항목=기타항목)
        
    except Exception as e:
        print(f"카드영수증 변환 오류: {str(e)}")
        print(f"오류 발생 시점의 request.form: {dict(request.form)}")
        flash(f'카드영수증 변환 중 오류가 발생했습니다: {str(e)}', 'error')
        
        # 주문내역 입력값들도 제대로 수집해서 유지
        html_content = request.form.get('html_content', '')
        option_count = int(request.form.get('option_count', 5))
        print(f"예외 처리 시 html_content 길이: {len(html_content) if html_content else 0}")
        print(f"예외 처리 시 option_count: {option_count}")
        
        # 옵션별 입력 필드 수집
        option_inputs = []
        for i in range(option_count):
            option = {
                '상품명': request.form.get(f'option_{i}_상품명', ''),
                '옵션명': request.form.get(f'option_{i}_옵션명', ''),
                '수량': request.form.get(f'option_{i}_수량(숫자만)', ''),
                '상품가격': request.form.get(f'option_{i}_상품가격(숫자만)', ''),
                '상품이미지': request.form.get(f'option_{i}_상품이미지', ''),
                '상품 할인 전 금액': request.form.get(f'option_{i}_상품 할인 전 금액(숫자만, 0입력시 미출력)', '')
            }
            option_inputs.append(option)
        
        # 기타 항목 수집
        기타필드 = [
            "스토어명", "배송비", "수령자명", "연락처", "주소",
            "주문금액(총결제금액, 숫자만)", "상품금액(숫자만)", 
            "쿠폰할인(숫자만, 0입력시 div삭제)", "결제배송비(숫자만)", "카드결제금액(숫자만)"
        ]
        기타항목 = {field: request.form.get(field, '') for field in 기타필드}
        
        # 디버깅: 예외 처리 시 템플릿 렌더링 데이터 로깅
        print("=== 예외 처리 시 템플릿 렌더링 데이터 ===")
        print(f"html_content 길이: {len(html_content) if html_content else 0}")
        print(f"option_count: {option_count}")
        print(f"option_inputs 개수: {len(option_inputs)}")
        print(f"기타항목 개수: {len(기타항목)}")
        
        return render_template('naverpay.html', 
                             order_result=None, 
                             card_result=None, 
                             card_data=None, 
                             active_tab='card',
                             # 주문내역 입력값들 완전히 유지
                             html_content=html_content,
                             option_count=option_count,
                             option_inputs=option_inputs,
                             기타항목=기타항목)

@app.route('/naverpay/extract-order-info', methods=['POST'])
def extract_order_info():
    """주문내역에서 정보 추출 - 기존 load_order_file 로직"""
    try:
        data = request.get_json()
        html_content = data.get('html_content', '')
        
        if not html_content:
            return jsonify({'success': False, 'error': 'HTML 내용이 없습니다.'})
        
        # 주문내역에서 정보 추출
        order_info = naverpay_converter.load_order_info_from_html(html_content)
        
        return jsonify({
            'success': True,
            'product': order_info['product'],
            'approval_amount': order_info['approval_amount'],
            'total': order_info['total']
        })
        
    except Exception as e:
        print(f"주문내역 정보 추출 오류: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/history')
def history():
    """변환 히스토리 조회"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 최근 50개 작업 조회
        cursor.execute('''
            SELECT id, tool_type, input_filename, output_filename, status, created_at
            FROM jobs 
            ORDER BY created_at DESC 
            LIMIT 50
        ''')
        
        jobs = cursor.fetchall()
        conn.close()
        
        # 작업 데이터 포맷팅
        formatted_jobs = []
        for job in jobs:
            formatted_jobs.append({
                'id': job[0],
                'tool_type': job[1],
                'input_filename': job[2],
                'output_filename': job[3],
                'status': job[4],
                'created_at': job[5]
            })
        
        return render_template('history.html', jobs=formatted_jobs)
        
    except Exception as e:
        print(f"히스토리 조회 오류: {str(e)}")
        flash(f'히스토리 조회 중 오류가 발생했습니다: {str(e)}', 'error')
        return render_template('history.html', jobs=[])

@app.route('/history/delete/<int:job_id>', methods=['POST'])
def delete_history_item(job_id):
    """히스토리 항목 삭제"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 작업 삭제
        cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
        conn.commit()
        conn.close()
        
        flash('히스토리 항목이 삭제되었습니다.', 'success')
        
    except Exception as e:
        print(f"히스토리 삭제 오류: {str(e)}")
        flash(f'히스토리 삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('history'))

@app.route('/history/clear', methods=['POST'])
def clear_history():
    """전체 히스토리 삭제"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 모든 작업 삭제
        cursor.execute('DELETE FROM jobs')
        conn.commit()
        conn.close()
        
        flash('전체 히스토리가 삭제되었습니다.', 'success')
        
    except Exception as e:
        print(f"히스토리 전체 삭제 오류: {str(e)}")
        flash(f'히스토리 전체 삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('history'))


# 파일 다운로드
@app.route('/download/<filename>')
def download_file(filename):
    try:
        # 보안을 위해 파일명 검증
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            flash('잘못된 파일명입니다.', 'error')
            return redirect(url_for('index'))
        
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        
        # 파일 존재 확인
        if not os.path.exists(file_path):
            flash('파일을 찾을 수 없습니다.', 'error')
            return redirect(url_for('index'))
        
        # 파일 다운로드 - 텍스트 파일로 다운로드
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,  # 다운로드 시 파일명 지정
            mimetype='text/plain'  # 텍스트 파일임을 명시
        )
        
    except Exception as e:
        print(f"다운로드 오류: {str(e)}")  # 서버 로그에 오류 출력
        flash('파일 다운로드 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('index'))


@app.route('/monitor')
def monitor():
    """시스템 모니터링 대시보드"""
    try:
        # 로그 파일 정보 수집
        log_folder = 'logs'
        log_files = []
        
        if os.path.exists(log_folder):
            for filename in os.listdir(log_folder):
                if filename.endswith('.log'):
                    filepath = os.path.join(log_folder, filename)
                    stat = os.stat(filepath)
                    log_files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'path': filepath
                    })
        
        # 데이터베이스 통계
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        # 총 작업 수
        cursor.execute('SELECT COUNT(*) FROM jobs')
        total_jobs = cursor.fetchone()[0]
        
        # 성공한 작업 수
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE status = "completed"')
        successful_jobs = cursor.fetchone()[0]
        
        # 실패한 작업 수
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE status = "failed"')
        failed_jobs = cursor.fetchone()[0]
        
        # 최근 24시간 작업 수
        cursor.execute('SELECT COUNT(*) FROM jobs WHERE created_at > datetime("now", "-1 day")')
        recent_jobs = cursor.fetchone()[0]
        
        # 도구별 통계
        cursor.execute('SELECT tool_type, COUNT(*) FROM jobs GROUP BY tool_type')
        tool_stats = dict(cursor.fetchall())
        
        conn.close()
        
        # 시스템 정보
        import psutil
        system_info = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent
        }
        
        return render_template('monitor.html', 
                             log_files=log_files,
                             total_jobs=total_jobs,
                             successful_jobs=successful_jobs,
                             failed_jobs=failed_jobs,
                             recent_jobs=recent_jobs,
                             tool_stats=tool_stats,
                             system_info=system_info)
        
    except Exception as e:
        app.logger.error(f"모니터링 대시보드 오류: {str(e)}")
        flash(f'모니터링 대시보드 로드 중 오류가 발생했습니다: {str(e)}', 'error')
        return render_template('monitor.html', 
                             log_files=[],
                             total_jobs=0,
                             successful_jobs=0,
                             failed_jobs=0,
                             recent_jobs=0,
                             tool_stats={},
                             system_info={'cpu_percent': 0, 'memory_percent': 0, 'disk_usage': 0})

@app.route('/monitor/logs/<filename>')
def view_log_file(filename):
    """로그 파일 내용 조회"""
    try:
        # 보안을 위해 파일명 검증
        if not filename or '..' in filename or '/' in filename or '\\' in filename:
            flash('잘못된 파일명입니다.', 'error')
            return redirect(url_for('monitor'))
        
        filepath = os.path.join('logs', filename)
        
        if not os.path.exists(filepath):
            flash('로그 파일을 찾을 수 없습니다.', 'error')
            return redirect(url_for('monitor'))
        
        # 로그 파일 내용 읽기 (최근 1000줄)
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 최근 1000줄만 표시
        recent_lines = lines[-1000:] if len(lines) > 1000 else lines
        
        return render_template('log_viewer.html', 
                             filename=filename, 
                             lines=recent_lines,
                             total_lines=len(lines))
        
    except Exception as e:
        app.logger.error(f"로그 파일 조회 오류: {str(e)}")
        flash(f'로그 파일 조회 중 오류가 발생했습니다: {str(e)}', 'error')
        return redirect(url_for('monitor'))

# 저장된 입력값 불러오기 API
@app.route('/api/get-saved-inputs/<tool_type>')
def get_saved_inputs_api(tool_type):
    """저장된 입력값들을 JSON으로 반환"""
    try:
        saved_inputs = get_saved_inputs(tool_type)
        
        # JavaScript가 기대하는 구조로 변환
        inputs = []
        for item in saved_inputs:
            inputs.append({
                'id': item['id'],
                'input_data': item['data'],  # 'data'를 'input_data'로 변경
                'created_at': item['created_at']
            })
        
        return jsonify({
            'success': True,
            'inputs': inputs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# 특정 입력값 불러오기 API
@app.route('/api/load-input/<int:input_id>')
def load_specific_input(input_id):
    """특정 입력값을 불러오기"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT input_data FROM saved_inputs WHERE id = ?
        ''', (input_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            import json
            return jsonify({
                'success': True,
                'input_data': json.loads(result[0])
            })
        else:
            return jsonify({
                'success': False,
                'error': '입력값을 찾을 수 없습니다.'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


if __name__ == '__main__':
    # 데이터베이스 초기화
    init_db()
    
    # 로컬 개발에서만 쓰임. Render에서는 Start Command가 gunicorn이므로 실행되지 않음.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)