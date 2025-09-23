"""
네이버페이 옵션/카드영수증 통합 수정기 모듈
기존 multi_option_retry.py의 모든 기능을 웹용으로 완전 포팅
"""

import re
from bs4 import BeautifulSoup
import datetime
import json
import os

class NaverpayConverter:
    def __init__(self):
        self.sample_ul = None
        self.load_sample_code()
    
    def load_sample_code(self):
        """샘플 코드 파일을 로드"""
        try:
            sample_path = os.path.join(os.path.dirname(__file__), '..', '옵션 여러 개 샘플코드(사은품없음).txt')
            with open(sample_path, 'r', encoding='utf-8') as f:
                self.sample_ul = f.read()
        except FileNotFoundError:
            self.sample_ul = ""
    
    def replace_ul(self, html, sample_ul):
        """옵션 ul 부분을 샘플코드로 교체 (ul~Notice_section-notice__aTOa2 포함)"""
        pattern = (
            r'(<ul class="ProductInfoSection_product-list__LNSQt"[^>]*>'
            r'[\s\S]*?Notice_section-notice__aTOa2[\s\S]*?</div>\s*</ul>)'
        )
        return re.sub(pattern, sample_ul, html, count=1)
    
    def replace_purchase_date_in_sample(self, sample_ul, purchase_date):
        """샘플코드 내의 '구매확정일 ...' 부분만 모두 입력값으로 교체"""
        return re.sub(r'구매확정일\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\([^)]+\)', purchase_date, sample_ul)
    
    def trim_option_blocks(self, sample_ul, option_count):
        """샘플코드 내에서 옵션 li를 옵션명 기준이 아니라, li 개수만큼만 남기고 뒤에서부터 삭제하는 방식으로 변경"""
        soup = BeautifulSoup(sample_ul, "html.parser")
        ul = soup.find("ul", class_="ProductInfoSection_product-list__LNSQt")
        if not ul:
            return sample_ul
        # li 리스트 추출
        li_list = ul.find_all("li", class_="ProductInfoSection_product-item__dipCB")
        # 옵션 개수만큼만 li 남기고 나머지 삭제
        for li in li_list[option_count:]:
            li.decompose()
        # 각 li 내부에서 '사은품' li 삭제
        for li in ul.find_all("li", class_="ProductDetail_option__AC1PJ"):
            badge = li.find("span", class_="Badge_type-basic__HO5JF")
            if badge and '사은품' in badge.get_text():
                li.decompose()
        return str(soup)
    
    def format_price(self, val):
        """금액 포맷 함수"""
        try:
            return f"{int(str(val).replace(',', '')):,}"
        except:
            return str(val)
    
    def calculate_supply_amount(self, approval_amount):
        """공급가액 계산"""
        try:
            amount = int(str(approval_amount).replace(',', ''))
            supply_amount = round(amount / 1.1)
            return self.format_price(supply_amount)
        except:
            return "0"
    
    def calculate_tax_amount(self, approval_amount, supply_amount):
        """부가세액 계산"""
        try:
            approval = int(str(approval_amount).replace(',', ''))
            supply = int(str(supply_amount).replace(',', ''))
            tax_amount = approval - supply
            return self.format_price(tax_amount)
        except:
            return "0"
    
    def sanitize_filename(self, filename):
        """Windows 파일명에서 허용되지 않는 문자를 안전한 문자로 변환하는 함수"""
        # Windows에서 허용되지 않는 문자들을 안전한 문자로 변환
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
        safe_filename = filename
        for char in invalid_chars:
            safe_filename = safe_filename.replace(char, '_')
        
        # 파일명이 너무 길 경우 자르기 (Windows 파일명 최대 길이는 255자, 확장자 포함)
        if len(safe_filename) > 240:  # .txt 확장자를 고려하여 240자로 제한
            safe_filename = safe_filename[:240]
        
        return safe_filename
    
    def process_order_html(self, html_content, option_count, purchase_date):
        """주문내역 HTML 처리 - 기존 on_replace 함수 로직"""
        # 구매확정일 자동 추출
        if not purchase_date:
            for line in html_content.splitlines():
                if "구매확정일" in line:
                    text = re.sub('<[^<]+?>', '', line)
                    m = re.search(r'구매확정일\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*\([^)]+\)', text)
                    if m:
                        purchase_date = m.group()
                        break
        
        if not purchase_date:
            raise ValueError("구매확정일을 찾을 수 없습니다.")
        
        # 샘플코드에 구매확정일 적용
        sample_ul_with_date = self.replace_purchase_date_in_sample(self.sample_ul, purchase_date)
        
        # 옵션 개수만큼 샘플코드 조정
        trimmed_ul = self.trim_option_blocks(sample_ul_with_date, option_count)
        
        # HTML에 적용
        replaced_html = self.replace_ul(html_content, trimmed_ul)
        
        return replaced_html, trimmed_ul
    
    def apply_order_fields(self, final_html, trimmed_ul, option_inputs, 기타항목):
        """주문내역 필드 적용 - 기존 ask_and_replace_fields의 on_ok 함수 로직"""
        result = final_html
        
        # 스토어명, 배송비 치환
        result = re.sub(r'(<strong class="ProductStore_title__iJmfU"><span class="blind">판매자명</span>)[^<]+', r'\g<1>' + 기타항목["스토어명"], result)
        result = re.sub(r'(<div class="ProductStore_delivery__BivAy">)[^<]+', f'\g<1>{기타항목["배송비"]}', result)
        
        # 옵션별 상품 정보 치환
        soup2 = BeautifulSoup(result, "html.parser")
        option_lis2 = soup2.find_all("li", class_="ProductInfoSection_product-item__dipCB")
        
        for idx, li in enumerate(option_lis2):
            if idx >= len(option_inputs):
                break
                
            # 상품명 치환
            strong = li.find("strong", class_="ProductDetail_name__KnKyo")
            if strong:
                for c in list(strong.contents):
                    if getattr(c, 'name', None) != "span":
                        c.extract()
                strong.append(option_inputs[idx]['상품명'])
            
            # 옵션명 치환
            spans = li.find_all("span", class_="ProductDetail_text__KHWhA")
            if spans and len(spans) > 0:
                spans[0].string = option_inputs[idx]['옵션명']
            
            # 수량 치환
            if spans and len(spans) > 1:
                em = spans[1].find("em")
                if em:
                    em.string = option_inputs[idx]['수량'] + "개"
            
            # 가격 치환
            price_span = li.find("span", class_="ProductDetail_price__g34o4")
            if price_span:
                price_span.clear()
                price_span.append(f"{int(option_inputs[idx]['상품가격']):,}원")
            
            # 이미지 치환
            img_tag = li.find("img")
            if img_tag:
                img_tag["src"] = option_inputs[idx]['상품이미지']
            
            # 할인 전 금액 처리
            s_tag = None
            if price_span and price_span.next_sibling and getattr(price_span.next_sibling, 'name', None) == 's' and 'ProductDetail_deleted__bSH1G' in price_span.next_sibling.get('class', []):
                s_tag = price_span.next_sibling
            
            if option_inputs[idx]['상품 할인 전 금액'] and option_inputs[idx]['상품 할인 전 금액'] != '0':
                if s_tag:
                    s_tag.string = option_inputs[idx]['상품 할인 전 금액']
                else:
                    new_s = soup2.new_tag('s', **{'class': 'ProductDetail_deleted__bSH1G'})
                    new_s.string = option_inputs[idx]['상품 할인 전 금액']
                    price_span.insert_after(new_s)
            else:
                if s_tag:
                    s_tag.decompose()
        
        result = str(soup2)
        
        # 배송지 정보 치환
        result = re.sub(r'(<strong class="DeliveryContent_name__fyClB"><span class="blind">배송지명</span>)[^<]+', f'\g<1>{기타항목["수령자명"]}({기타항목["수령자명"]})', result)
        result = re.sub(r'(<span class="DeliveryContent_phone__f0k\+a"><span class="blind">연락처</span>)[^<]+', f'\g<1>{기타항목["연락처"]}', result)
        result = re.sub(r'(<div class="DeliveryContent_area-address__XsMLS"><span class="blind">주소</span>)[^<]+', f'\g<1>{기타항목["주소"]}', result)
        
        # 금액 정보 치환
        result = re.sub(r'(<dd class="Summary_area-value__BcN0d">총 )[\d,]+', f'\g<1>{int(기타항목["주문금액(총결제금액, 숫자만)"]):,}', result)
        result = re.sub(r'(<div class="SubSummary_item-detail__QFXCA">\s*<dt[^>]*>\s*<span class="SubSummary_label__9VC8U">상품금액</span>.*?</dt>\s*<dd class="SubSummary_area-value__2c7V6">)[^<]+', f'\g<1>{int(기타항목["상품금액(숫자만)"]):,}원', result, flags=re.DOTALL)
        
        # 쿠폰할인 처리
        if 기타항목['쿠폰할인(숫자만, 0입력시 div삭제)'] == '0':
            soup3 = BeautifulSoup(result, "html.parser")
            for div in soup3.find_all("div", class_="SubSummary_item-detail__QFXCA"):
                label = div.find("span", class_="SubSummary_label__9VC8U")
                if label and "쿠폰할인" in label.get_text():
                    div.decompose()
            result = str(soup3)
        else:
            result = re.sub(r'(<span class="SubSummary_label__9VC8U">쿠폰할인</span>[\s\S]*?<dd class="SubSummary_area-value__2c7V6">)-[\d,]+원', f'\g<1>-{int(기타항목["쿠폰할인(숫자만, 0입력시 div삭제)"]):,}원', result)
        
        # 배송비, 카드결제금액, 네이버포인트 치환
        result = re.sub(r'(<span class="SubSummary_label__9VC8U">배송비</span></dt><dd class="SubSummary_area-value__2c7V6">)[\d,]+', f'\g<1>{int(기타항목["결제배송비(숫자만)"]):,}', result)
        result = re.sub(r'(<dd class="Summary_area-value__BcN0d">)[\d,]+원', f'\g<1>{int(기타항목["카드결제금액(숫자만)"]):,}원', result)
        
        # 네이버포인트 계산
        try:
            point = int(기타항목['주문금액(총결제금액, 숫자만)'].replace(",", "")) * 0.03
            기타항목['네이버포인트'] = f"{int(point):,}"
        except:
            기타항목['네이버포인트'] = "0"
        
        result = re.sub(r'(<em class="OrderDetailPointBanner_point__Z5z-O">최대 )[\d,]+원', f'\g<1>{기타항목["네이버포인트"]}원', result)
        
        return result
    
    def process_card_html(self, html_content, card_fields):
        """카드영수증 HTML 처리 - 기존 save_card_receipt 함수 로직"""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 값 치환 함수
        def set_dd(dt_text, value):
            dt = soup.find("dt", string=dt_text)
            if dt:
                dd = dt.find_next_sibling("dd")
                if dd:
                    dd.string = value
        
        # 각 필드 치환
        set_dd("상품명", card_fields["product"])
        set_dd("판매자상호", card_fields["seller"])
        set_dd("대표자명", card_fields["ceo"])
        
        # 사업자등록번호: 000-00-00000 형식으로 변환
        biznum = card_fields["biznum"]
        numbers = re.sub(r'[^\d]', '', biznum)
        if len(numbers) == 10:
            biznum_fmt = f"{numbers[:3]}-{numbers[3:5]}-{numbers[5:]}"
        else:
            biznum_fmt = biznum
        set_dd("사업자등록번호", biznum_fmt)
        
        set_dd("전화번호", card_fields["phone"])
        set_dd("사업장주소", card_fields["address"])
        set_dd("승인금액", card_fields["approval_amount"])
        set_dd("공급가액", card_fields["supply_amount"])
        set_dd("부가세액", card_fields["tax_amount"])
        set_dd("봉사료", card_fields["service_fee"])
        
        # 합계(하단 div)
        total_div = soup.find("div", class_="Summary_summary__wHW36")
        if total_div:
            total_div.string = card_fields["total"]
        
        return str(soup)
    
    def load_order_info_from_html(self, html_content):
        """주문내역 HTML에서 상품명과 주문금액 추출 - 기존 load_order_file 함수 로직"""
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 상품명: 옵션1번 상품명
        product = ""
        option1 = soup.find_all("li", class_="ProductInfoSection_product-item__dipCB")
        if option1:
            strong = option1[0].find("strong", class_="ProductDetail_name__KnKyo")
            if strong:
                for c in strong.contents:
                    if getattr(c, 'name', None) != "span":
                        product = c.string.strip() if c.string else ""
        
        # 주문금액(총결제금액): 11번 항목
        total = ""
        total_tag = soup.find("dd", class_="Summary_area-value__BcN0d")
        if total_tag:
            total = re.sub(r"[^\d]", "", total_tag.get_text())
        
        return {
            "product": product,
            "approval_amount": self.format_price(total),
            "total": self.format_price(total)
        }
    
    def get_default_purchase_date(self):
        """기본 구매확정일 반환"""
        today = datetime.datetime.now()
        weekdays = ['월', '화', '수', '목', '금', '토', '일']
        weekday = weekdays[today.weekday()]
        return f"구매확정일 {today.strftime('%Y. %m. %d.')} ({weekday})"


