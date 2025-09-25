import pandas as pd
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import logging
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def save_screenshot(page, filename):
    """스크린샷 저장"""
    try:
        page.screenshot(path=f"screenshots/{filename}.png")
        logger.info(f"스크린샷 저장: {filename}")
    except:
        pass

def wait_for_ajax(page, timeout=5000):
    """AJAX 요청 완료 대기"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        time.sleep(2)

def clean_text(text):
    """텍스트 정제"""
    if not text:
        return ""
    return ' '.join(text.split()).strip()

def extract_table_data(table_element):
    """테이블에서 데이터 추출"""
    data = {}
    try:
        rows = table_element.locator("tr").all()
        for row in rows:
            ths = row.locator("th").all()
            tds = row.locator("td").all()

            # th-td 쌍 처리
            for i, th in enumerate(ths):
                if i < len(tds):
                    key = clean_text(th.inner_text())
                    value = clean_text(tds[i].inner_text())
                    if key:
                        data[key] = value
    except Exception as e:
        logger.error(f"테이블 파싱 오류: {e}")
    return data

def search_course(page, course_name):
    """교육과정 검색 및 결과 반환"""
    logger.info(f"검색 시작: {course_name}")

    try:
        # 메인 페이지 이동
        page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=30000)
        wait_for_ajax(page)

        # 검색어 입력
        search_input = page.locator("#planngCrseNm")
        search_input.fill("")
        search_input.fill(course_name)

        # 검색 실행 - 여러 방법 시도
        # 방법 1: Enter 키
        page.keyboard.press("Enter")
        wait_for_ajax(page, 5000)

        # 검색 결과 확인
        results = page.locator('.curriculum__box').all()
        logger.info(f"검색 결과 수: {len(results)}")

        if len(results) == 0:
            # 다시 검색 버튼으로 시도
            search_btn = page.locator('button:has-text("검색")')
            if search_btn.count() > 0:
                search_btn.click()
                wait_for_ajax(page, 5000)
                results = page.locator('.curriculum__box').all()
                logger.info(f"재검색 결과 수: {len(results)}")

        return results

    except Exception as e:
        logger.error(f"검색 중 오류: {e}")
        return []

def navigate_to_detail(page, result_element):
    """검색 결과에서 상세 페이지로 이동"""
    try:
        # onclick 속성 추출
        link = result_element.locator('.curriculum__thumbnail a, a.btn.solid').first
        onclick = link.get_attribute('onclick')

        if onclick:
            logger.info(f"onclick 속성: {onclick}")

            # JavaScript 실행으로 페이지 이동
            page.evaluate(onclick)
            wait_for_ajax(page, 10000)

            # URL 변경 확인
            current_url = page.url
            logger.info(f"현재 URL: {current_url}")

            if "paa0040" in current_url:
                return True

        # 직접 클릭 시도
        link.click()
        wait_for_ajax(page, 10000)

        return "paa0040" in page.url

    except Exception as e:
        logger.error(f"상세 페이지 이동 실패: {e}")
        return False

def parse_detail_page_v2(page):
    """상세 페이지 파싱 - 개선된 버전"""
    course_data = {}

    # URL 저장
    course_data['상세페이지_URL'] = page.url

    # 페이지 HTML 전체 가져오기 (디버깅용)
    try:
        page_content = page.content()

        # 1. 교육과정명
        for selector in ['h3.tit', 'h3.sub_cont_title_h3', '.page-title', 'h3']:
            elem = page.locator(selector).first
            if elem.count() > 0:
                title = elem.inner_text()
                if title and '교육과정' not in title:  # 제목이 아닌 텍스트 제외
                    course_data['교육과정명'] = clean_text(title)
                    logger.info(f"교육과정명: {course_data['교육과정명']}")
                    break

        # 2. 모든 테이블 찾기
        tables = page.locator('table').all()
        logger.info(f"찾은 테이블 수: {len(tables)}")

        for idx, table in enumerate(tables):
            try:
                table_text = table.inner_text()

                # 신청정보 테이블
                if '교육대상' in table_text or '신청기간' in table_text or '교육기간' in table_text:
                    logger.info(f"신청정보 테이블 발견 (테이블 {idx})")
                    table_data = extract_table_data(table)
                    for key, value in table_data.items():
                        course_data[f'신청_{key}'] = value

                # 수료기준 테이블
                elif '출석' in table_text and '수료기준' in table_text:
                    logger.info(f"수료기준 테이블 발견 (테이블 {idx})")
                    # 헤더와 데이터 분리
                    headers = [clean_text(th.inner_text()) for th in table.locator('th').all()]
                    values = [clean_text(td.inner_text()) for td in table.locator('td').all()]

                    if len(headers) == len(values):
                        for h, v in zip(headers, values):
                            course_data[f'수료_{h}'] = v

                # 교육구성 테이블
                elif '교과목' in table_text or '강사명' in table_text:
                    logger.info(f"교육구성 테이블 발견 (테이블 {idx})")
                    headers = [clean_text(th.inner_text()) for th in table.locator('thead th').all()]

                    if not headers:
                        headers = [clean_text(th.inner_text()) for th in table.locator('tr').first.locator('th').all()]

                    if headers:
                        curriculum_data = []
                        rows = table.locator('tbody tr').all()
                        if not rows:
                            rows = table.locator('tr').all()[1:]  # 첫 행 제외

                        for row in rows:
                            cells = [clean_text(td.inner_text()) for td in row.locator('td').all()]
                            if cells and len(cells) == len(headers):
                                curriculum_data.append(dict(zip(headers, cells)))

                        if curriculum_data:
                            course_data['교육구성'] = json.dumps(curriculum_data, ensure_ascii=False)

                # 추천교육과정 테이블
                elif '추천' in table_text:
                    logger.info(f"추천교육과정 테이블 발견 (테이블 {idx})")
                    if '추천 교육과정이 없습니다' in table_text:
                        course_data['추천교육과정'] = '없음'
                    else:
                        # 추천 교육과정 파싱
                        headers = [clean_text(th.inner_text()) for th in table.locator('thead th').all()]
                        if headers:
                            reco_data = []
                            rows = table.locator('tbody tr').all()
                            for row in rows:
                                cells = [clean_text(td.inner_text()) for td in row.locator('td').all()]
                                if cells and len(cells) == len(headers):
                                    reco_data.append(dict(zip(headers, cells)))

                            if reco_data:
                                course_data['추천교육과정'] = json.dumps(reco_data, ensure_ascii=False)

            except Exception as e:
                logger.error(f"테이블 {idx} 파싱 오류: {e}")

        # 3. 교육소개 섹션 찾기
        for selector in ['#introduction', '.education-intro', 'div:has(h4:has-text("교육소개"))']:
            elem = page.locator(selector).first
            if elem.count() > 0:
                intro_text = elem.inner_text()
                if intro_text and len(intro_text) > 10:
                    # '교육소개' 헤더 제거
                    intro_text = intro_text.replace('교육소개', '', 1).strip()
                    course_data['교육소개'] = clean_text(intro_text)
                    logger.info(f"교육소개: {course_data['교육소개'][:50]}...")
                    break

    except Exception as e:
        logger.error(f"상세 페이지 파싱 오류: {e}")
        course_data['파싱오류'] = str(e)

    return course_data

def scrape_single_course(course_name, browser, debug=False):
    """단일 교육과정 스크래핑"""
    logger.info(f"\n{'='*50}")
    logger.info(f"스크래핑 시작: {course_name}")

    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080}
    )
    page = context.new_page()

    course_info = {
        '원본_교육과정명': course_name,
        '스크래핑_시각': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    try:
        # 1. 검색
        results = search_course(page, course_name)

        if len(results) == 0:
            logger.warning("검색 결과 없음")
            course_info['스크래핑결과'] = '검색 결과 없음'
            return course_info

        # 첫 번째 결과 정보 수집
        first_result = results[0]
        title_elem = first_result.locator('.curriculum__info--title').first
        if title_elem.count() > 0:
            found_title = clean_text(title_elem.inner_text())
            course_info['검색_결과_제목'] = found_title
            logger.info(f"찾은 교육과정: {found_title}")

        # 2. 상세 페이지 이동
        if navigate_to_detail(page, first_result):
            logger.info("상세 페이지 이동 성공")

            # 3. 상세 정보 파싱
            detail_data = parse_detail_page_v2(page)
            course_info.update(detail_data)

            # 파싱 결과 확인
            parsed_fields = [k for k in detail_data.keys() if not k.startswith('파싱오류')]
            logger.info(f"파싱된 필드 수: {len(parsed_fields)}")
            logger.info(f"파싱된 필드: {', '.join(parsed_fields[:5])}...")

            course_info['스크래핑결과'] = '성공' if len(parsed_fields) > 3 else '부분 성공'
        else:
            logger.error("상세 페이지 이동 실패")
            course_info['스크래핑결과'] = '상세 페이지 접근 실패'

    except Exception as e:
        logger.error(f"스크래핑 오류: {e}")
        course_info['스크래핑결과'] = f'오류: {str(e)[:100]}'

    finally:
        context.close()

    return course_info

def main():
    """메인 실행 함수"""
    # CSV 파일 로드
    try:
        df = pd.read_csv(r"C:\KOHI\work.csv")
        course_names = df.iloc[:, 0].tolist()
        logger.info(f"총 {len(course_names)}개 교육과정 로드")
    except Exception as e:
        logger.error(f"CSV 로드 실패: {e}")
        return

    # 스크린샷 폴더 생성
    import os
    os.makedirs('screenshots', exist_ok=True)

    results = []

    with sync_playwright() as p:
        # 디버그 모드: 첫 번째 과정만 visible 브라우저로
        browser = p.chromium.launch(headless=False)

        # 첫 번째 과정 테스트
        logger.info("\n=== 첫 번째 과정 테스트 (디버그 모드) ===")
        result = scrape_single_course(course_names[0], browser, debug=True)
        results.append(result)

        # 결과 출력
        logger.info("\n=== 첫 번째 과정 결과 ===")
        for key, value in result.items():
            if isinstance(value, str) and len(value) > 100:
                logger.info(f"{key}: {value[:100]}...")
            else:
                logger.info(f"{key}: {value}")

        input("\n첫 번째 과정 완료. Enter를 눌러 나머지 과정 진행...")
        browser.close()

        # 나머지 과정들 headless로 처리
        if len(course_names) > 1:
            browser = p.chromium.launch(headless=True)

            for i, course_name in enumerate(course_names[1:], 2):
                logger.info(f"\n진행 상황: {i}/{len(course_names)}")
                result = scrape_single_course(course_name, browser)
                results.append(result)

                # 10개마다 임시 저장
                if i % 10 == 0:
                    temp_df = pd.DataFrame(results)
                    temp_df.to_csv(r"C:\KOHI\scraped_results_temp.csv", index=False, encoding='utf-8-sig')
                    logger.info(f"임시 저장 완료 ({i}개)")

            browser.close()

    # 최종 결과 저장
    final_df = pd.DataFrame(results)
    final_df.to_csv(r"C:\KOHI\scraped_results_final.csv", index=False, encoding='utf-8-sig')

    # 통계 출력
    logger.info("\n" + "="*50)
    logger.info("스크래핑 완료!")
    logger.info(f"총 처리: {len(results)}개")

    if '스크래핑결과' in final_df.columns:
        stats = final_df['스크래핑결과'].value_counts()
        for status, count in stats.items():
            logger.info(f"  - {status}: {count}개")

    logger.info(f"결과 파일: C:\\KOHI\\scraped_results_final.csv")

if __name__ == "__main__":
    main()