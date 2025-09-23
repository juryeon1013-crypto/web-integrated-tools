"""
도매꾹 주문내역 수정기 모듈
기존 domeggook_order_modifier.py의 핵심 로직을 웹용으로 변환
"""

import re
import random
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import os

class DomeggookConverter:
    def __init__(self):
        self.html_template = None
        self.card_template = None
        self.load_templates()
    
    def load_templates(self):
        """HTML 템플릿 파일들을 로드"""
        try:
            # 주문내역 템플릿
            template_path = os.path.join(os.path.dirname(__file__), '..', '주문내역 body 태그 전체.txt')
            with open(template_path, 'r', encoding='utf-8') as f:
                self.html_template = f.read()
        except FileNotFoundError:
            self.html_template = ""
        
        try:
            # 카드영수증 템플릿
            card_path = os.path.join(os.path.dirname(__file__), '..', '카드영수증 body 태그 전체.txt')
            with open(card_path, 'r', encoding='utf-8') as f:
                self.card_template = f.read()
        except FileNotFoundError:
            self.card_template = ""
    
    def modify_order(self, html_content, order_data):
        """
        주문내역 HTML을 수정 (기존 프로그램의 모든 기능 포함)
        
        Args:
            html_content (str): 원본 HTML 내용
            order_data (dict): 수정할 주문 정보
        
        Returns:
            str: 수정된 HTML 내용
        """
        if not html_content:
            return "HTML 내용이 없습니다."
        
        try:
            # BeautifulSoup으로 HTML 파싱
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 옵션 삭제 처리
            option_count = int(order_data.get('option_count', 5))
            if option_count < 1 or option_count > 5:
                option_count = 5
            
            # 삭제할 옵션 개수 계산 (5 - 사용자가 입력한 개수)
            delete_count = 5 - option_count
            
            # 삭제할 옵션들 (아래에서부터 순서대로)
            options_to_delete = ["그린", "핑크", "오렌지", "블랙", "옐로우"]
            
            # 삭제할 개수만큼 아래에서부터 삭제
            for i in range(delete_count):
                option_name = options_to_delete[i]
                for tr in soup.find_all('tr'):
                    td = tr.find('td', align="left")
                    if td and option_name in td.get_text():
                        tr.decompose()
                        break
            
            # 1. 주문번호 수정
            order_number = order_data.get('order_number', '0202')
            pattern = r'OR6461\d{4}'
            replacement = 'OR6461' + order_number
            html_content = re.sub(pattern, replacement, html_content)
            
            # 수정된 HTML로 다시 파싱
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 2. 상품제목 수정
            product_title = order_data.get('product_title', '아르코에어')
            random_number = str(random.randint(10000, 99999))
            new_product_number = "299" + random_number
            
            for a in soup.find_all('a'):
                text = a.get_text().strip()
                if text.startswith('[299'):
                    new_text = f'[{new_product_number}] {product_title}'
                    a.string = new_text
                    break
            
            # 3. 공급사이름 수정
            supplier_name = order_data.get('supplier_name', '아르코에어')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '공급사이름':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = supplier_name
                    break
            
            # 4. 공급사이메일 수정
            supplier_email = order_data.get('supplier_email', '아르코에어')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '공급사이메일':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = supplier_email
                    break
            
            # 5. 공급사연락처 수정
            supplier_phone = order_data.get('supplier_phone', '010-0000-1234')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '공급사연락처':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = supplier_phone
                    break
            
            # 6. 주문수량 수정
            quantity = order_data.get('quantity', '10')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '주문수량':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        font_tag = next_td.find('font', color="#cc0000")
                        if font_tag:
                            b_tag = font_tag.find('b')
                            if b_tag:
                                b_tag.string = f"{quantity}개"
                    break
            
            # 7. 결제금액 수정
            payment_amount = order_data.get('payment_amount', '200000')
            formatted_amount = self.format_number(payment_amount)
            
            for td in soup.find_all('td'):
                if td.get_text().strip() == '결제금액':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        font_tag = next_td.find('font', color="#cc0000")
                        if font_tag:
                            b_tag = font_tag.find('b')
                            if b_tag:
                                b_tag.string = f"{formatted_amount}원"
                    break
            
            # 8. 상품비 수정 (7번과 동일)
            for td in soup.find_all('td'):
                if td.get_text().strip() == '상품비':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = f"{formatted_amount}원"
                    break
            
            # 9. 배송비 수정 (고정값)
            for td in soup.find_all('td'):
                if td.get_text().strip() == '배송비':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = "주문시결제 0원"
                    break
            
            # 10. 결제방법 수정 (7번과 동일)
            for td in soup.find_all('td'):
                if td.get_text().strip() == '결제방법':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        b_tag = next_td.find('b', style="color:#cc0000")
                        if b_tag and '카드결제액' in b_tag.get_text():
                            b_tag.string = f"카드결제액 {formatted_amount}원"
                    break
            
            # 11. 수령자이름 수정
            recipient_name = order_data.get('recipient_name', '아르코에어')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '수령자이름':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = recipient_name
                    break
            
            # 12. 수령지주소 수정
            address = order_data.get('address', '아르코에어')
            for td in soup.find_all('td'):
                if td.get_text().strip() == '수령지주소':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.clear()
                        next_td.append(recipient_name)
                        next_td.append(soup.new_tag('br'))
                        next_td.append(address)
                    break
            
            # 13. 휴대전화 수정
            phone = order_data.get('phone', '01080809090')
            phone_digits = ''.join(filter(str.isdigit, phone))
            if len(phone_digits) == 11:
                formatted_phone = f"{phone_digits[:3]}-{phone_digits[3:7]}-{phone_digits[7:]}"
            else:
                formatted_phone = phone
                
            for td in soup.find_all('td'):
                if td.get_text().strip() == '휴대전화':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = formatted_phone
                    break
            
            # 14. 송장번호 삭제
            for b in soup.find_all('b'):
                if '510214500263' in b.get_text():
                    b.decompose()
                    break
            
            # 15. 주문일시 수정
            order_date_input = order_data.get('order_date', '20250602')
            if len(order_date_input) == 8:
                order_date = f"{order_date_input[:4]}/{order_date_input[4:6]}/{order_date_input[6:8]}"
            else:
                order_date = order_date_input
            
            # 임의 시간 생성
            random_hour = random.randint(0, 23)
            random_minute = random.randint(0, 59)
            random_second = random.randint(0, 59)
            random_time = f"{random_hour:02d}:{random_minute:02d}:{random_second:02d}"
            
            for td in soup.find_all('td'):
                if td.get_text().strip() == '주문일시':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = f"{order_date} {random_time}"
                    break
            
            # 16. 결제일시 수정 (15번 날짜 + 24초)
            payment_time = self.add_seconds(random_time, 24)
            for td in soup.find_all('td'):
                if td.get_text().strip() == '결제일시':
                    next_td = td.find_next_sibling('td')
                    if next_td:
                        next_td.string = f"{order_date} {payment_time}"
                    break
            
            # 18. 상품주문옵션 수정
            self.modify_product_options(soup, order_data, option_count)
            
            # 17. 주문상태기록 수정
            modified_html = self.modify_order_status(str(soup), order_date, random_time, formatted_amount)
            
            return modified_html
            
        except Exception as e:
            return f"HTML 수정 중 오류가 발생했습니다: {str(e)}"
    
    def modify_product_options(self, soup, order_data, option_count):
        """상품주문옵션 수정"""
        for td in soup.find_all('td'):
            if td.get_text().strip() == '상품주문옵션':
                option_table = td.find_next_sibling('td')
                if option_table:
                    tbody = option_table.find('tbody')
                    if tbody:
                        tbody.clear()
                        
                        # 새로운 옵션들 추가
                        for i in range(option_count):
                            option_num = i + 1
                            option_name = order_data.get(f'option_{option_num}_name', f'여성용/옐로우')
                            option_quantity = order_data.get(f'option_{option_num}_quantity', '1')
                            option_price = order_data.get(f'option_{option_num}_price', '2550')
                            
                            formatted_price = self.format_number(option_price)
                            
                            # 새로운 tr 생성
                            new_tr = soup.new_tag('tr')
                            if i > 0:
                                new_tr['style'] = 'border-top:1px solid #ccc'
                            
                            # 상품명 td
                            name_td = soup.new_tag('td', align="left", style="padding:7px 3px 4px 3px; line-height:14px;")
                            if i > 0:
                                name_td['style'] = "padding:7px 3px 4px 3px; line-height:14px; border-top:1px solid #ccc;"
                            name_td.string = option_name
                            new_tr.append(name_td)
                            
                            # 개수 td
                            quantity_td = soup.new_tag('td', align="right", style="padding:7px 3px 4px 3px; line-height:14px;")
                            if i > 0:
                                quantity_td['style'] = "padding:7px 3px 4px 3px; line-height:14px; border-top:1px solid #ccc;"
                            quantity_td.string = f"{option_quantity}개"
                            new_tr.append(quantity_td)
                            
                            # 금액 td
                            price_td = soup.new_tag('td', align="right", style="padding:7px 3px 4px 3px; line-height:14px;")
                            if i > 0:
                                price_td['style'] = "padding:7px 3px 4px 3px; line-height:14px; border-top:1px solid #ccc;"
                            price_td.string = f"{formatted_price}원"
                            new_tr.append(price_td)
                            
                            tbody.append(new_tr)
                break
    
    def modify_order_status(self, html_content, order_date, order_time, payment_amount):
        """주문상태기록 수정"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 기준 시간 (15번 랜덤시간 + 2초)
        base_time = datetime.strptime(order_time, "%H:%M:%S")
        base_time = base_time + timedelta(seconds=2)
        
        # 각 상태별 시간 계산
        card_payment_time = base_time + timedelta(seconds=25)
        order_confirm_time = base_time + timedelta(seconds=5)
        shipping_start_time = base_time + timedelta(hours=17, minutes=31, seconds=46)
        shipping_complete_time = base_time + timedelta(days=2, hours=0, minutes=22, seconds=15)
        purchase_confirm_time = base_time + timedelta(days=10, hours=15, minutes=43, seconds=41)
        
        # 날짜 계산
        order_date_obj = datetime.strptime(order_date, "%Y/%m/%d")
        shipping_start_date = order_date_obj + timedelta(days=1)
        shipping_complete_date = order_date_obj + timedelta(days=2)
        purchase_confirm_date = order_date_obj + timedelta(days=10)
        
        # 새로운 상태기록 생성
        new_status = (
            f'{purchase_confirm_date.strftime("%Y/%m/%d")} {purchase_confirm_time.strftime("%H:%M:%S")} : 상품구매확정 (자동처리)\n'
            f'{shipping_complete_date.strftime("%Y/%m/%d")} {shipping_complete_time.strftime("%H:%M:%S")} : 상품배송완료\n'
            f'{shipping_start_date.strftime("%Y/%m/%d")} {shipping_start_time.strftime("%H:%M:%S")} : 상품배송시작\n'
            f'{order_date} {order_confirm_time.strftime("%H:%M:%S")} : 발주확인\n'
            f'{order_date} {card_payment_time.strftime("%H:%M:%S")} : 카드결제 {payment_amount}원\n'
            f'{order_date} {base_time.strftime("%H:%M:%S")} : 주문정보입력\n'
        )
        
        # 주문상태기록 td 찾기 및 수정
        for td in soup.find_all('td'):
            if td.get_text().strip() == '주문상태기록':
                next_td = td.find_next_sibling('td')
                if next_td:
                    next_td.clear()
                    lines = new_status.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip():
                            next_td.append(line)
                            if i < len(lines) - 1:
                                next_td.append(soup.new_tag('br'))
                break
        
        return str(soup)
    
    def format_number(self, number_str):
        """숫자에 천단위 쉼표 추가"""
        try:
            number = int(number_str.replace(',', ''))
            return f"{number:,}"
        except:
            return number_str
    
    def add_seconds(self, time_str, seconds):
        """시간에 초를 더함"""
        try:
            time_obj = datetime.strptime(time_str, "%H:%M:%S")
            new_time = time_obj + timedelta(seconds=seconds)
            return new_time.strftime("%H:%M:%S")
        except:
            return time_str
    
    def create_card_receipt(self, order_data):
        """카드영수증 생성 - 기존 프로그램 로직 완전 복사"""
        if not self.card_template:
            return "카드영수증 템플릿을 찾을 수 없습니다."
        
        try:
            # 기존 프로그램의 calculate_card_values 로직 완전 복사
            order_date = order_data.get('order_date', '20250602')
            payment_amount_str = order_data.get('payment_amount', '200000')
            payment_amount = int(payment_amount_str.replace(',', ''))
            order_number = order_data.get('order_number', '0202')
            product_title = order_data.get('product_title', '아르코에어')
            supplier_phone = order_data.get('supplier_phone', '010-0000-1234')
            
            # 1. 주문번호 계산 - JavaScript에서 전송한 값 사용
            card_order_number = order_data.get('card_order_number', '')
            if not card_order_number:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                if ' ' in order_date:  # 공백이 있으면 날짜와 시간이 분리된 형식
                    date_part = order_date.split(' ')[0]  # 날짜 부분만 추출
                    if len(date_part) >= 8:  # YYYYMMDD 형식
                        date_formatted = date_part[:8]  # YYYYMMDD 그대로 사용
                    else:
                        date_formatted = "20250101"  # 기본값
                elif len(order_date) >= 8:  # YYYYMMDD 형식
                    date_formatted = order_date[:8]  # YYYYMMDD 그대로 사용
                else:
                    date_formatted = "20250101"  # 기본값
                
                random_suffix = str(random.randint(100, 999))
                card_order_number = date_formatted + "165233" + random_suffix
            
            # 2. 거래일시 계산 - JavaScript에서 전송한 값 사용
            transaction_time = order_data.get('transaction_time', '')
            if not transaction_time:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                random_hour = random.randint(0, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                random_time = f"{random_hour:02d}:{random_minute:02d}:{random_second:02d}"
                
                if ' ' in order_date:  # 공백이 있으면 날짜와 시간이 분리된 형식
                    date_part, time_part = order_date.split(' ', 1)
                    if len(date_part) >= 8:  # YYYYMMDD 형식
                        transaction_time = f"{date_part[:4]}/{date_part[4:6]}/{date_part[6:8]} {random_time}"
                    else:
                        transaction_time = f"{date_formatted[:4]}/{date_formatted[4:6]}/{date_formatted[6:8]} {random_time}"
                else:
                    transaction_time = f"{date_formatted[:4]}/{date_formatted[4:6]}/{date_formatted[6:8]} {random_time}"
            
            # 3. 승인번호 계산 - JavaScript에서 전송한 값 사용
            approval_number = order_data.get('approval_number', '')
            if not approval_number:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                approval_number = "3026" + str(random.randint(1000, 9999))
            
            # 4. 상품정보 계산 - JavaScript에서 전송한 값 사용
            product_info = order_data.get('product_info', '')
            if not product_info:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                final_order_number = "OR6461" + order_number
                product_info = f"{final_order_number} {product_title}"
            
            # 5. 공급가 계산 - JavaScript에서 전송한 값 사용
            supply_amount_str = order_data.get('supply_amount', '')
            if supply_amount_str:
                supply_amount = int(supply_amount_str)
            else:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                supply_amount = int(payment_amount / 1.1)
            
            # 6. 부가세 계산 - JavaScript에서 전송한 값 사용
            vat_amount_str = order_data.get('vat_amount', '')
            if vat_amount_str:
                vat_amount = int(vat_amount_str)
            else:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                vat_amount = payment_amount - supply_amount
            
            # 7. 면세금액 - JavaScript에서 전송한 값 사용
            tax_free_amount_str = order_data.get('tax_free_amount', '')
            if tax_free_amount_str:
                tax_free_amount = int(tax_free_amount_str)
            else:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                tax_free_amount = 0
            
            # 8. 합계금액 - JavaScript에서 전송한 값 사용
            total_amount_str = order_data.get('total_amount', '')
            if total_amount_str:
                total_amount = int(total_amount_str)
            else:
                # JavaScript에서 값을 못 보내면 기존 로직 사용
                total_amount = payment_amount
            
            # 공급자 연락처 처리 (기존 프로그램과 동일)
            if supplier_phone:
                supplier_contact = f"Tel.{supplier_phone}"
            else:
                supplier_contact = "Tel.053-639-6981"
            
            # 카드영수증 HTML 수정 (기존 프로그램의 modify_card_html 로직 완전 복사)
            modified_html = self.modify_card_html({
                'card_order_number': card_order_number,
                'transaction_time': transaction_time,
                'approval_number': approval_number,
                'product_info': product_info,
                'supply_amount': supply_amount,
                'vat_amount': vat_amount,
                'tax_free_amount': tax_free_amount,
                'total_amount': total_amount,
                'store_name': order_data.get('store_name', '아르코에어'),
                'business_number': order_data.get('business_number', '1234567890'),
                'ceo_name': order_data.get('ceo_name', '아르코에어'),
                'supplier_address': order_data.get('supplier_address', '아르코에어'),
                'supplier_contact': supplier_contact
            })
            
            return modified_html
            
        except Exception as e:
            return f"카드영수증 생성 중 오류가 발생했습니다: {str(e)}"
    
    def modify_card_html(self, card_data):
        """카드영수증 HTML 수정 - 기존 프로그램 로직 완전 복사"""
        soup = BeautifulSoup(self.card_template, 'html.parser')
        
        # 2. 거래일시 수정 (더 유연한 패턴) - Keep as re.sub as user said it works
        transaction_time = card_data['transaction_time']
        transaction_time_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_date.gif")
        if transaction_time_img:
            transaction_time_td_label = transaction_time_img.find_parent('td')
            if transaction_time_td_label:
                transaction_time_value_tr = transaction_time_td_label.find_parent('tr').find_next_sibling('tr')
                if transaction_time_value_tr:
                    transaction_time_value_td = transaction_time_value_tr.find('td', class_='num', style="padding-left:5")
                    if transaction_time_value_td:
                        original_text = transaction_time_value_td.string
                        if original_text:
                            date_time_pattern = r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})'
                            new_text = re.sub(date_time_pattern, transaction_time, original_text)
                            transaction_time_value_td.string = new_text
        
        # 3. 승인번호 수정 - BeautifulSoup으로 정확한 텍스트 치환
        approval_number = card_data['approval_number']
        approval_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_approval.gif")
        if approval_img:
            approval_td_label = approval_img.find_parent('td')
            if approval_td_label:
                approval_value_tr = approval_td_label.find_parent('tr').find_next_sibling('tr')
                if approval_value_tr:
                    approval_value_td = approval_value_tr.find('td', style="padding-left:5")
                    if approval_value_td:
                        approval_value_td.string = approval_number + '\n                                                            '
        
        # 4. 상품정보 수정 - BeautifulSoup으로 정확한 텍스트 치환
        product_info = card_data['product_info']
        product_info_td = soup.find('td', style="word-break:break-all;padding-left:5;padding-top:2")
        if product_info_td:
            # 상품정보 td의 모든 텍스트 내용을 확인
            full_text = product_info_td.get_text()
            if '상품정보 :' in full_text and 'OR64619579' in full_text:
                # 기존 텍스트를 모두 제거하고 새로운 구조로 교체
                product_info_td.clear()
                # "상품정보 : " + <br> + 새로운 상품정보
                product_info_td.append("상품정보 : ")
                product_info_td.append(soup.new_tag('br'))
                product_info_td.append(product_info)
        
        # 5. 공급가 치환 - BeautifulSoup으로 정확한 숫자 치환
        supply_amount = card_data['supply_amount']
        supply_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_supply.gif")
        if supply_img:
            supply_td_label = supply_img.find_parent('td')
            if supply_td_label:
                supply_value_tr = supply_td_label.find_parent('tr')
                if supply_value_tr:
                    # 공급가 td에서 class="num_b"인 td들을 찾기
                    num_b_tds = supply_value_tr.find_all('td', class_='num_b')
                    if num_b_tds:
                        # 금액을 문자열로 변환
                        amount_str = str(supply_amount)
                        # 6자리 숫자를 뒤에서부터 채우기 (1의 자리부터)
                        for i in range(6):
                            if i < len(num_b_tds):
                                if i < len(amount_str):
                                    digit = amount_str[-(i+1)]  # 뒤에서부터 가져오기
                                    if digit == '0':
                                        num_b_tds[-(i+1)].string = '0'  # 0일 때는 '0'으로 표시
                                    else:
                                        num_b_tds[-(i+1)].string = digit
                                else:
                                    # 금액보다 높은 자리는 빈칸으로
                                    num_b_tds[-(i+1)].string = '\xa0'
        
        # 6. 부가세 치환 - BeautifulSoup으로 정확한 숫자 치환
        vat_amount = card_data['vat_amount']
        vat_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_vat.gif")
        if vat_img:
            vat_td_label = vat_img.find_parent('td')
            if vat_td_label:
                vat_value_tr = vat_td_label.find_parent('tr')
                if vat_value_tr:
                    # 부가세 td에서 class="num_b"인 td들을 찾기
                    num_b_tds = vat_value_tr.find_all('td', class_='num_b')
                    if num_b_tds:
                        # 금액을 문자열로 변환
                        amount_str = str(vat_amount)
                        # 6자리 숫자를 뒤에서부터 채우기 (1의 자리부터)
                        for i in range(6):
                            if i < len(num_b_tds):
                                if i < len(amount_str):
                                    digit = amount_str[-(i+1)]  # 뒤에서부터 가져오기
                                    if digit == '0':
                                        num_b_tds[-(i+1)].string = '0'  # 0일 때는 '0'으로 표시
                                    else:
                                        num_b_tds[-(i+1)].string = digit
                                else:
                                    # 금액보다 높은 자리는 빈칸으로
                                    num_b_tds[-(i+1)].string = '\xa0'
        
        # 7. 면세금액 치환 - Keep as is
        html_content_str = str(soup)
        taxfree_amount = card_data['tax_free_amount']
        html_content_str = self.fill_money_cells_regex(html_content_str, taxfree_amount, 't_amount01.gif')
        soup = BeautifulSoup(html_content_str, 'html.parser')
        
        # 8. 합계금액 치환 - BeautifulSoup으로 정확한 숫자 치환
        total_amount = card_data['total_amount']
        total_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_total.gif")
        if total_img:
            total_td_label = total_img.find_parent('td')
            if total_td_label:
                total_value_tr = total_td_label.find_parent('tr')
                if total_value_tr:
                    # 합계금액 td에서 class="num_b"인 td들을 찾기
                    num_b_tds = total_value_tr.find_all('td', class_='num_b')
                    if num_b_tds:
                        # 금액을 문자열로 변환
                        amount_str = str(total_amount)
                        # 6자리 숫자를 뒤에서부터 채우기 (1의 자리부터)
                        for i in range(6):
                            if i < len(num_b_tds):
                                if i < len(amount_str):
                                    digit = amount_str[-(i+1)]  # 뒤에서부터 가져오기
                                    if digit == '0':
                                        num_b_tds[-(i+1)].string = '0'  # 0일 때는 '0'으로 표시
                                    else:
                                        num_b_tds[-(i+1)].string = digit
                                else:
                                    # 금액보다 높은 자리는 빈칸으로
                                    num_b_tds[-(i+1)].string = '\xa0'
        
        # 9. 상점명 수정 - BeautifulSoup로 정확한 텍스트 치환
        store_name = card_data['store_name']
        store_name_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_sub_name.gif")
        if store_name_img:
            store_name_td_label = store_name_img.find_parent('td')
            if store_name_td_label:
                store_name_value_tr = store_name_td_label.find_parent('tr').find_next_sibling('tr')
                if store_name_value_tr:
                    store_name_value_td = store_name_value_tr.find('td', bgcolor="#F6F7F5", style="padding:3 2 2 5")
                    if store_name_value_td:
                        store_name_value_td.string = store_name + '\n                                                            '
        
        # 10. 사업자등록번호 수정 - Keep as re.sub as user said it works
        business_number = card_data['business_number']
        if business_number.isdigit() and len(business_number) == 10:
            formatted_number = f"{business_number[:3]}-{business_number[3:5]}-{business_number[5:]}"
        else:
            formatted_number = business_number
        html_content_str = str(soup)
        pattern = r'(\d{3}-\d{2}-\d{5})'
        html_content_str = re.sub(pattern, formatted_number, html_content_str)
        soup = BeautifulSoup(html_content_str, 'html.parser')
        
        # 11. 대표자명 수정 - BeautifulSoup로 정확한 텍스트 치환
        ceo_name = card_data['ceo_name']
        supplier_info_table = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_supplier_info.gif").find_parent('table')
        if supplier_info_table:
            ceo_name_img_in_supplier = supplier_info_table.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_master.gif")
            if ceo_name_img_in_supplier:
                ceo_name_td_label = ceo_name_img_in_supplier.find_parent('td')
                if ceo_name_td_label:
                    ceo_name_value_tr = ceo_name_td_label.find_parent('tr').find_next_sibling('tr')
                    if ceo_name_value_tr:
                        ceo_name_value_td = ceo_name_value_tr.find('td', bgcolor="#F6F7F5", style="padding-left:5")
                        if ceo_name_value_td:
                            ceo_name_value_td.string = ceo_name + '\n                                                            '
        
        # 12. 공급자 연락처 수정 - Keep as re.sub as user said it works
        supplier_contact = card_data['supplier_contact']
        html_content_str = str(soup)
        pattern = r'(Tel\.\d{3}-\d{3}-\d{4})'
        html_content_str = re.sub(pattern, supplier_contact, html_content_str)
        soup = BeautifulSoup(html_content_str, 'html.parser')
        
        # 13. 공급자 주소 수정 - BeautifulSoup으로 정확한 텍스트 치환
        supplier_address = card_data['supplier_address']
        address_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_address01.gif")
        if address_img:
            address_td_label = address_img.find_parent('td')
            if address_td_label:
                address_value_tr = address_td_label.find_parent('tr').find_next_sibling('tr')
                if address_value_tr:
                    address_value_td = address_value_tr.find('td', bgcolor="#F6F7F5", style="padding:3 2 2 5")
                    if address_value_td:
                        address_value_td.string = supplier_address + '\n                                                            '
        
        # 1. 주문번호 수정 (가장 마지막에 실행) - BeautifulSoup으로 정확한 텍스트 치환
        card_order_number = card_data['card_order_number']
        order_no_img = soup.find('img', src="/WEB_SERVER/wmp/etc/image/sale_slip/t_order_no.gif")
        if order_no_img:
            order_no_td_label = order_no_img.find_parent('td')
            if order_no_td_label:
                order_no_value_tr = order_no_td_label.find_parent('tr').find_next_sibling('tr')
                if order_no_value_tr:
                    order_no_value_td = order_no_value_tr.find('td', class_='num', style="padding-left:5")
                    if order_no_value_td:
                        order_no_value_td.string = card_order_number + '\n                                                            '
        
        return str(soup)
        
    def fill_money_cells_regex(self, html_content, amount, img_src):
        """정규식을 사용하여 금액 셀들을 채우는 함수 - 기존 프로그램과 완전 동일"""
        amount_str = str(amount)
        
        # 해당 이미지를 포함하는 tr 태그를 찾기 위한 패턴
        img_pattern = re.escape(img_src)
        
        # 간단한 패턴으로 td class="num_b" 태그들을 찾아서 교체
        # 뒤에서부터 일의자리부터 채우기
        td_pattern = r'(<td class="num_b">)[^<]*(</td>)'
        
        def replace_td(match, digit):
            if digit == '0':
                return match.group(1) + '\xa0' + match.group(2)
            else:
                return match.group(1) + digit + match.group(2)
        
        # 6자리 숫자를 뒤에서부터 채우기
        for i in range(6):
            if i < len(amount_str):
                digit = amount_str[-(i+1)]
                html_content = re.sub(td_pattern, lambda m: replace_td(m, digit), html_content, count=1)
            else:
                html_content = re.sub(td_pattern, lambda m: replace_td(m, '0'), html_content, count=1)
        
        return html_content
    
    def get_default_template(self):
        """기본 HTML 템플릿 반환"""
        return self.html_template
    
    def validate_html(self, html_content):
        """HTML 내용 유효성 검사"""
        if not html_content:
            return False, "HTML 내용이 비어있습니다."
        
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            if not soup.find("body"):
                return False, "올바른 HTML 형식이 아닙니다."
            return True, "유효한 HTML입니다."
        except Exception as e:
            return False, f"HTML 파싱 오류: {str(e)}"


