import pandas as pd
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import logging
from datetime import datetime
import re

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_advanced.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KohiScraper:
    """KOHI 교육 사이트 스크래퍼"""

    def __init__(self, headless=True):
        self.headless = headless
        self.base_url = "https://edu.kohi.or.kr"
        self.search_url = f"{self.base_url}/pt/pa/paa/BD_paa0010l.do"
        self.results = []

    def clean_text(self, text):
        """텍스트 정제"""
        if not text:
            return ""
        # 공백 정규화
        text = re.sub(r'\s+', ' ', text)
        # 앞뒤 공백 제거
        return text.strip()

    def wait_for_search_results(self, page):
        """검색 결과 로딩 대기"""
        try:
            # 여러 조건 중 하나라도 만족하면 통과
            page.wait_for_selector('.curriculum__box', state='visible', timeout=10000)
            return True
        except:
            try:
                page.wait_for_selector('.curriculum__wrap', state='visible', timeout=5000)
                return True
            except:
                try:
                    # "검색 결과가 없습니다" 메시지 확인
                    no_result = page.locator('text=검색 결과가 없습니다').count() > 0
                    if no_result:
                        logger.info("검색 결과 없음 메시지 감지")
                        return False
                except:
                    pass

        # 최종 대기
        time.sleep(3)
        return True

    def search_course_javascript(self, page, course_name):
        """JavaScript를 통한 검색 실행"""
        logger.info(f"JavaScript 검색 실행: {course_name}")

        try:
            # 검색어 입력
            page.evaluate(f"""
                document.getElementById('planngCrseNm').value = '{course_name}';
            """)

            # searchAct() 함수 실행 (Agent 분석 결과 활용)
            page.evaluate("""
                if (typeof searchAct === 'function') {
                    searchAct();
                } else if (typeof searchList === 'function') {
                    searchList();
                } else {
                    // 폼 제출
                    document.querySelector('form').submit();
                }
            """)

            # 검색 결과 대기
            self.wait_for_search_results(page)

            # 결과 수집
            results = page.locator('.curriculum__box').all()
            logger.info(f"JavaScript 검색 결과: {len(results)}개")
            return results

        except Exception as e:
            logger.error(f"JavaScript 검색 실패: {e}")
            return []

    def get_course_codes(self, element):
        """교육과정 코드 추출"""
        try:
            # onclick 속성에서 코드 추출
            onclick = element.locator('a').first.get_attribute('onclick')
            if onclick:
                # btn_selectPaa0040('A2511069','251003086') 형식에서 추출
                match = re.search(r"btn_selectPaa0040\('([^']+)','([^']+)'\)", onclick)
                if match:
                    crse_code = match.group(1)
                    grno_code = match.group(2)
                    logger.info(f"코드 추출: crse={crse_code}, grno={grno_code}")
                    return crse_code, grno_code
        except Exception as e:
            logger.error(f"코드 추출 실패: {e}")
        return None, None

    def navigate_to_detail_javascript(self, page, crse_code, grno_code):
        """JavaScript를 통한 상세 페이지 이동"""
        try:
            logger.info(f"상세 페이지 이동: crse={crse_code}, grno={grno_code}")

            # btn_selectPaa0040 함수 실행
            page.evaluate(f"""
                if (typeof btn_selectPaa0040 === 'function') {{
                    btn_selectPaa0040('{crse_code}', '{grno_code}');
                }} else {{
                    // 직접 URL 이동
                    window.location.href = '/pt/pa/paa/BD_paa0040d.do?crseCode={crse_code}&crseGrnoCode={grno_code}';
                }}
            """)

            # 페이지 로딩 대기
            page.wait_for_load_state('domcontentloaded')
            time.sleep(2)

            # URL 확인
            if 'paa0040' in page.url:
                logger.info(f"상세 페이지 도착: {page.url}")
                return True
            return False

        except Exception as e:
            logger.error(f"상세 페이지 이동 실패: {e}")
            return False

    def parse_detail_enhanced(self, page):
        """향상된 상세 페이지 파싱"""
        data = {}

        try:
            # 페이지 전체 HTML 가져오기
            html_content = page.content()

            # 1. 교육과정명
            selectors_title = [
                'h3.tit',
                'h3.sub_cont_title_h3',
                '.page-title',
                'h3:has-text("교육")',
                'div.title-area h3'
            ]

            for selector in selectors_title:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    title = self.clean_text(elem.inner_text())
                    if title and len(title) > 2:
                        data['교육과정명'] = title
                        logger.info(f"교육과정명: {title}")
                        break

            # 2. 교육소개 - ID와 h4 두 가지 방법
            intro_found = False

            # ID로 시도
            intro_elem = page.locator('#introduction')
            if intro_elem.count() > 0:
                intro_text = intro_elem.inner_text()
                if intro_text:
                    # '교육소개' 텍스트 제거
                    intro_text = re.sub(r'^교육소개\s*', '', intro_text)
                    data['교육소개'] = self.clean_text(intro_text)
                    intro_found = True
                    logger.info("교육소개 찾음 (ID)")

            # h4 헤더로 시도
            if not intro_found:
                intro_h4 = page.locator('h4:has-text("교육소개")')
                if intro_h4.count() > 0:
                    # 다음 형제 요소들 수집
                    siblings = page.evaluate("""
                        const h4 = document.querySelector('h4:has-text("교육소개")');
                        if (h4) {
                            let content = '';
                            let next = h4.nextElementSibling;
                            while (next && next.tagName !== 'H4') {
                                content += next.innerText + ' ';
                                next = next.nextElementSibling;
                            }
                            return content;
                        }
                        return '';
                    """)
                    if siblings:
                        data['교육소개'] = self.clean_text(siblings)
                        logger.info("교육소개 찾음 (H4)")

            # 3. 테이블 데이터 추출
            tables = page.locator('table').all()
            logger.info(f"테이블 수: {len(tables)}")

            for idx, table in enumerate(tables):
                try:
                    # 테이블 HTML 가져오기
                    table_html = table.inner_html()
                    table_text = table.inner_text()

                    # 신청정보 테이블
                    if any(keyword in table_text for keyword in ['교육대상', '신청기간', '교육기간', '교육시간']):
                        logger.info(f"신청정보 테이블 (인덱스 {idx})")
                        rows = table.locator('tr').all()
                        for row in rows:
                            ths = row.locator('th').all()
                            tds = row.locator('td').all()
                            for i, th in enumerate(ths):
                                if i < len(tds):
                                    key = self.clean_text(th.inner_text())
                                    value = self.clean_text(tds[i].inner_text())
                                    if key:
                                        data[f'신청_{key}'] = value

                    # 수료기준 테이블
                    elif '출석' in table_text and '수료' in table_text:
                        logger.info(f"수료기준 테이블 (인덱스 {idx})")
                        # 첫 행이 헤더
                        headers = []
                        values = []

                        rows = table.locator('tr').all()
                        if len(rows) >= 2:
                            # 헤더 행
                            header_row = rows[0]
                            headers = [self.clean_text(th.inner_text()) for th in header_row.locator('th').all()]

                            # 데이터 행
                            data_row = rows[1]
                            values = [self.clean_text(td.inner_text()) for td in data_row.locator('td').all()]

                            if len(headers) == len(values):
                                for h, v in zip(headers, values):
                                    if h:
                                        data[f'수료_{h}'] = v

                    # 교육구성 테이블
                    elif any(keyword in table_text for keyword in ['교과목', '강사', '교육일자']):
                        logger.info(f"교육구성 테이블 (인덱스 {idx})")

                        # 헤더 찾기
                        thead = table.locator('thead')
                        if thead.count() > 0:
                            headers = [self.clean_text(th.inner_text()) for th in thead.locator('th').all()]
                        else:
                            # thead가 없으면 첫 tr에서 th 찾기
                            first_row = table.locator('tr').first
                            headers = [self.clean_text(th.inner_text()) for th in first_row.locator('th').all()]

                        if headers:
                            # 데이터 행 수집
                            tbody = table.locator('tbody')
                            if tbody.count() > 0:
                                data_rows = tbody.locator('tr').all()
                            else:
                                data_rows = table.locator('tr').all()[1:]

                            curriculum_data = []
                            for row in data_rows:
                                cells = [self.clean_text(td.inner_text()) for td in row.locator('td').all()]
                                if cells and len(cells) == len(headers):
                                    row_dict = dict(zip(headers, cells))
                                    curriculum_data.append(row_dict)

                            if curriculum_data:
                                data['교육구성'] = json.dumps(curriculum_data, ensure_ascii=False)
                                data['교육구성_과목수'] = len(curriculum_data)

                    # 추천교육과정
                    elif '추천' in table_text:
                        logger.info(f"추천교육과정 테이블 (인덱스 {idx})")
                        if '추천 교육과정이 없습니다' in table_text:
                            data['추천교육과정'] = '없음'
                        else:
                            # 추천 과정 파싱
                            thead = table.locator('thead')
                            if thead.count() > 0:
                                headers = [self.clean_text(th.inner_text()) for th in thead.locator('th').all()]
                                tbody = table.locator('tbody')
                                if tbody.count() > 0:
                                    reco_data = []
                                    for row in tbody.locator('tr').all():
                                        cells = [self.clean_text(td.inner_text()) for td in row.locator('td').all()]
                                        if cells and len(cells) == len(headers):
                                            reco_data.append(dict(zip(headers, cells)))

                                    if reco_data:
                                        data['추천교육과정'] = json.dumps(reco_data, ensure_ascii=False)
                                        data['추천교육과정_수'] = len(reco_data)

                except Exception as e:
                    logger.error(f"테이블 {idx} 파싱 오류: {e}")

        except Exception as e:
            logger.error(f"상세 파싱 오류: {e}")
            data['파싱오류'] = str(e)[:200]

        return data

    def scrape_course(self, page, course_name):
        """단일 교육과정 스크래핑"""
        result = {
            '원본_교육과정명': course_name,
            '스크래핑_시각': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        try:
            # 메인 페이지로 이동
            page.goto(self.search_url, timeout=30000)
            page.wait_for_load_state('domcontentloaded')
            time.sleep(2)

            # JavaScript 검색 실행
            search_results = self.search_course_javascript(page, course_name)

            if not search_results:
                # 일반 검색 재시도
                logger.info("JavaScript 검색 실패, 일반 검색 시도")
                page.locator('#planngCrseNm').fill(course_name)
                page.keyboard.press('Enter')
                self.wait_for_search_results(page)
                search_results = page.locator('.curriculum__box').all()

            if not search_results:
                result['스크래핑결과'] = '검색 결과 없음'
                return result

            # 첫 번째 결과 선택
            first_result = search_results[0]

            # 검색 결과 제목 수집
            title_elem = first_result.locator('.curriculum__info--title')
            if title_elem.count() > 0:
                result['검색결과_제목'] = self.clean_text(title_elem.inner_text())

            # 교육과정 코드 추출
            crse_code, grno_code = self.get_course_codes(first_result)

            if crse_code and grno_code:
                # JavaScript로 상세 페이지 이동
                if self.navigate_to_detail_javascript(page, crse_code, grno_code):
                    # 상세 정보 파싱
                    detail_data = self.parse_detail_enhanced(page)
                    result.update(detail_data)
                    result['스크래핑결과'] = '성공'
                    result['교육과정_코드'] = crse_code
                    result['그룹_코드'] = grno_code
                else:
                    result['스크래핑결과'] = '상세 페이지 이동 실패'
            else:
                # 직접 클릭 시도
                logger.info("코드 추출 실패, 직접 클릭 시도")
                link = first_result.locator('a').first
                link.click()
                page.wait_for_load_state('domcontentloaded')
                time.sleep(2)

                if 'paa0040' in page.url:
                    detail_data = self.parse_detail_enhanced(page)
                    result.update(detail_data)
                    result['스크래핑결과'] = '성공 (직접 클릭)'
                else:
                    result['스크래핑결과'] = '상세 페이지 접근 실패'

        except Exception as e:
            logger.error(f"스크래핑 오류: {e}")
            result['스크래핑결과'] = f'오류: {str(e)[:100]}'

        return result

    def run(self, course_names, max_retry=2):
        """전체 스크래핑 실행"""
        logger.info(f"스크래핑 시작: {len(course_names)}개 교육과정")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )

            # 첫 번째 과정은 디버그 모드로
            if not self.headless:
                logger.info("=== 디버그 모드 (첫 번째 과정) ===")

            for idx, course_name in enumerate(course_names, 1):
                logger.info(f"\n[{idx}/{len(course_names)}] {course_name}")

                # 새 컨텍스트와 페이지 생성
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = context.new_page()

                # 스크래핑 시도
                result = None
                for attempt in range(max_retry):
                    if attempt > 0:
                        logger.info(f"재시도 {attempt}/{max_retry}")
                        time.sleep(2)

                    result = self.scrape_course(page, course_name)

                    if result.get('스크래핑결과') == '성공':
                        break

                self.results.append(result)
                context.close()

                # 진행상황 저장 (10개마다)
                if idx % 10 == 0:
                    self.save_temp_results()

                # 첫 번째 과정 후 로깅
                if idx == 1:
                    logger.info(f"첫 번째 과정 완료. 계속 진행중...")

            browser.close()

        return self.results

    def save_temp_results(self):
        """임시 결과 저장"""
        if self.results:
            df = pd.DataFrame(self.results)
            df.to_csv(r'C:\KOHI\scraped_temp.csv', index=False, encoding='utf-8-sig')
            logger.info(f"임시 저장: {len(self.results)}개")

    def save_final_results(self):
        """최종 결과 저장"""
        if self.results:
            df = pd.DataFrame(self.results)
            df.to_csv(r'C:\KOHI\scraped_final.csv', index=False, encoding='utf-8-sig')

            # 통계 출력
            logger.info("\n" + "="*50)
            logger.info(f"✅ 스크래핑 완료!")
            logger.info(f"총 처리: {len(self.results)}개")

            if '스크래핑결과' in df.columns:
                stats = df['스크래핑결과'].value_counts()
                for status, count in stats.items():
                    logger.info(f"  {status}: {count}개")

            # 파싱된 필드 통계
            field_counts = {}
            for col in df.columns:
                if not col.startswith('원본_') and not col.startswith('스크래핑'):
                    non_null = df[col].notna().sum()
                    if non_null > 0:
                        field_counts[col] = non_null

            logger.info("\n수집된 필드별 데이터 수:")
            for field, count in sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                logger.info(f"  {field}: {count}개")

            return df

def main():
    """메인 실행"""
    # CSV 로드
    try:
        df = pd.read_csv(r'C:\KOHI\work.csv')
        course_names = df.iloc[:, 0].tolist()
        logger.info(f"교육과정 로드: {len(course_names)}개")
    except Exception as e:
        logger.error(f"CSV 로드 실패: {e}")
        return

    # 스크래퍼 실행
    scraper = KohiScraper(headless=True)  # headless 모드로 실행
    scraper.run(course_names)
    result_df = scraper.save_final_results()

    logger.info(f"\n최종 결과: C:\\KOHI\\scraped_final.csv")

if __name__ == "__main__":
    main()