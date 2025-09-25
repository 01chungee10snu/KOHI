import pandas as pd
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time
import re

def clean_text(text):
    """텍스트 정제 함수"""
    if text:
        return text.strip().replace('\n', ' ').replace('\t', ' ').strip()
    return ""

def parse_detail_page(page):
    """
    상세 페이지의 모든 정보를 파싱하여 하나의 딕셔너리로 반환
    """
    course_data = {}

    try:
        # 디버그용 URL 저장
        course_data['상세페이지_URL'] = page.url
    except:
        pass

    # 1. 교육과정명 - 여러 selector 시도
    try:
        # h3.tit 또는 h3.sub_cont_title_h3 시도
        title = None
        for selector in ['h3.tit', 'h3.sub_cont_title_h3', '.curriculum-title', 'h3']:
            title_elem = page.locator(selector).first
            if title_elem.count() > 0:
                title = title_elem.inner_text(timeout=3000)
                if title:
                    course_data['교육과정명'] = clean_text(title)
                    break
    except Exception as e:
        print(f"    - 교육과정명 파싱 오류: {e}")

    # 2. 교육소개
    try:
        # ID로 시도
        intro_elem = page.locator('#introduction')
        if intro_elem.count() > 0:
            intro_text = intro_elem.inner_text(timeout=3000)
            course_data['교육소개'] = clean_text(intro_text)
        else:
            # h4 헤더로 시도
            intro_header = page.locator("h4:has-text('교육소개')")
            if intro_header.count() > 0:
                # 다음 형제 요소들 수집
                next_elem = intro_header.locator("xpath=following-sibling::*[1]")
                if next_elem.count() > 0:
                    intro_text = next_elem.inner_text(timeout=3000)
                    course_data['교육소개'] = clean_text(intro_text)
    except Exception as e:
        print(f"    - 교육소개 파싱 오류: {e}")

    # 3. 신청정보 파싱
    try:
        # 여러 방법으로 신청정보 테이블 찾기
        app_table = None

        # h4로 시도
        app_header = page.locator("h4:has-text('신청정보')")
        if app_header.count() > 0:
            app_table = app_header.locator("xpath=following-sibling::*//table").first

        # 테이블 직접 찾기
        if not app_table or app_table.count() == 0:
            tables = page.locator("table").all()
            for table in tables:
                table_text = table.inner_text()
                if '교육대상' in table_text or '신청기간' in table_text or '교육기간' in table_text:
                    app_table = table
                    break

        if app_table and app_table.count() > 0:
            rows = app_table.locator("tr").all()
            for row in rows:
                ths = row.locator("th").all()
                tds = row.locator("td").all()

                # th-td 쌍 처리
                for i, th in enumerate(ths):
                    if i < len(tds):
                        key = clean_text(th.inner_text())
                        value = clean_text(tds[i].inner_text())
                        if key:
                            key_name = key.replace('/', '_').replace(' ', '_')
                            course_data[f'신청_{key_name}'] = value
    except Exception as e:
        print(f"    - 신청정보 파싱 오류: {e}")

    # 4. 수료기준
    try:
        # 수료기준 테이블 찾기
        criteria_table = None

        criteria_header = page.locator("h4:has-text('수료기준')")
        if criteria_header.count() > 0:
            criteria_table = criteria_header.locator("xpath=following-sibling::*//table").first

        if not criteria_table or criteria_table.count() == 0:
            tables = page.locator("table").all()
            for table in tables:
                table_text = table.inner_text()
                if '출석' in table_text and '수료기준' in table_text:
                    criteria_table = table
                    break

        if criteria_table and criteria_table.count() > 0:
            # 헤더 행 파싱
            headers = []
            header_row = criteria_table.locator("tr").first
            if header_row.count() > 0:
                headers = [clean_text(th.inner_text()) for th in header_row.locator("th").all()]

            # 데이터 행 파싱
            data_rows = criteria_table.locator("tr").all()
            if len(data_rows) > 1:
                data_row = data_rows[1]  # 두 번째 행이 데이터
                values = [clean_text(td.inner_text()) for td in data_row.locator("td").all()]

                for i, header in enumerate(headers):
                    if i < len(values) and header:
                        course_data[f'수료기준_{header}'] = values[i]
    except Exception as e:
        print(f"    - 수료기준 파싱 오류: {e}")

    # 5. 교육구성
    try:
        # ID로 시도
        curriculum_elem = page.locator('#curriculumStructure')
        if curriculum_elem.count() > 0:
            curriculum_table = curriculum_elem.locator("table").first
        else:
            # h4 헤더로 시도
            curriculum_header = page.locator("h4:has-text('교육구성')")
            if curriculum_header.count() > 0:
                curriculum_table = curriculum_header.locator("xpath=following-sibling::*//table").first
            else:
                curriculum_table = None

        if curriculum_table and curriculum_table.count() > 0:
            headers = [clean_text(th.inner_text()) for th in curriculum_table.locator("thead th").all()]

            if not headers:  # thead가 없으면 첫 번째 tr에서 th 찾기
                first_row = curriculum_table.locator("tr").first
                if first_row.count() > 0:
                    headers = [clean_text(th.inner_text()) for th in first_row.locator("th").all()]

            # 데이터 행 수집
            tbody = curriculum_table.locator("tbody")
            if tbody.count() > 0:
                rows = tbody.locator("tr").all()
            else:
                rows = curriculum_table.locator("tr").all()[1:]  # 첫 행 제외

            curriculum_list = []
            for row in rows:
                cells = [clean_text(td.inner_text()) for td in row.locator("td").all()]
                if headers and cells and len(cells) == len(headers):
                    row_data = dict(zip(headers, cells))
                    curriculum_list.append(row_data)

            if curriculum_list:
                course_data['교육구성'] = json.dumps(curriculum_list, ensure_ascii=False)
    except Exception as e:
        print(f"    - 교육구성 파싱 오류: {e}")

    # 6. 추천교육과정
    try:
        # ID로 시도
        reco_elem = page.locator('#elearningCurriculum')
        if reco_elem.count() > 0:
            reco_text = reco_elem.inner_text()
            if "추천 교육과정이 없습니다" in reco_text:
                course_data['추천교육과정'] = "없음"
            else:
                # 테이블 파싱
                reco_table = reco_elem.locator("table").first
                if reco_table and reco_table.count() > 0:
                    headers = [clean_text(th.inner_text()) for th in reco_table.locator("thead th").all()]
                    rows = reco_table.locator("tbody tr").all()

                    reco_list = []
                    for row in rows:
                        cells = [clean_text(td.inner_text()) for td in row.locator("td").all()]
                        if headers and cells:
                            row_data = dict(zip(headers, cells))
                            reco_list.append(row_data)

                    if reco_list:
                        course_data['추천교육과정'] = json.dumps(reco_list, ensure_ascii=False)
        else:
            # h4 헤더로 시도
            reco_header = page.locator("h4:has-text('추천교육과정')")
            if reco_header.count() > 0:
                next_elem = reco_header.locator("xpath=following-sibling::*[1]")
                if next_elem.count() > 0:
                    reco_text = next_elem.inner_text()
                    if "추천 교육과정이 없습니다" in reco_text:
                        course_data['추천교육과정'] = "없음"
    except Exception as e:
        print(f"    - 추천교육과정 파싱 오류: {e}")

    return course_data


def run_scraper():
    """
    메인 스크래퍼 함수
    """
    try:
        input_df = pd.read_csv(r"C:\KOHI\work.csv")
        print(f"CSV 파일 로드 완료. 총 {len(input_df)}개 교육과정 발견")
    except FileNotFoundError:
        print("오류: C:\\KOHI\\work.csv 파일을 찾을 수 없습니다.")
        return
    except Exception as e:
        print(f"CSV 로드 오류: {e}")
        return

    results_list = []

    with sync_playwright() as p:
        # headless=True로 백그라운드 실행
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )

        page = context.new_page()

        for index, row in input_df.iterrows():
            # 첫 번째 컬럼을 교육과정명으로 간주
            course_name = str(row.iloc[0]).strip()
            print(f"\n[{index + 1}/{len(input_df)}] 스크래핑 시작: {course_name}")

            course_info = {'원본_교육과정명': course_name}

            try:
                # 1. 메인 페이지 이동
                print("  1. 메인 페이지 로딩...")
                page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)  # 페이지 안정화 대기

                # 2. 검색
                print(f"  2. 검색어 입력: {course_name}")
                search_input = page.locator("#planngCrseNm")
                search_input.fill("")  # 기존 텍스트 클리어
                search_input.fill(course_name)

                # Enter 키 대신 검색 버튼 클릭 시도
                search_btn = page.locator("#searchBtn")
                if search_btn.count() > 0:
                    search_btn.click()
                else:
                    page.keyboard.press("Enter")

                # 검색 결과 대기
                time.sleep(3)  # AJAX 로딩 대기

                # 3. 검색 결과 확인
                print("  3. 검색 결과 확인...")
                results = page.locator('.curriculum__box').all()

                if len(results) == 0:
                    # 다른 selector 시도
                    results = page.locator('.curriculum__wrap .curriculum__info').all()

                print(f"     - 검색 결과 수: {len(results)}")

                if len(results) == 0:
                    course_info['스크래핑결과'] = "검색 결과 없음"
                    results_list.append(course_info)
                    continue

                # 첫 번째 결과의 정보 수집
                first_title_elem = page.locator('.curriculum__info--title').first
                if first_title_elem.count() > 0:
                    found_title = first_title_elem.inner_text()
                    print(f"     - 찾은 교육과정: {found_title}")
                    course_info['검색결과_교육과정명'] = clean_text(found_title)

                # 4. 상세 페이지로 이동
                print("  4. 상세 페이지 이동...")

                # 썸네일 또는 수강신청 버튼 클릭
                thumbnail_link = page.locator('.curriculum__thumbnail a').first
                if thumbnail_link.count() == 0:
                    # 수강신청 버튼으로 시도
                    thumbnail_link = page.locator('a.btn.solid:has-text("수강신청")').first

                if thumbnail_link.count() > 0:
                    # onclick 속성에서 함수 호출 정보 추출
                    onclick_attr = thumbnail_link.get_attribute('onclick')
                    if onclick_attr and 'btn_selectPaa0040' in onclick_attr:
                        # 새 탭에서 열리는 것 방지
                        with page.expect_navigation(timeout=30000):
                            thumbnail_link.click()
                    else:
                        thumbnail_link.click()
                        page.wait_for_load_state("domcontentloaded")

                    time.sleep(2)  # 페이지 안정화 대기
                else:
                    print("     - 상세 페이지 링크를 찾을 수 없음")
                    course_info['스크래핑결과'] = "상세 페이지 링크 없음"
                    results_list.append(course_info)
                    continue

                # 5. 상세 정보 파싱
                print("  5. 상세 정보 파싱...")
                detail_data = parse_detail_page(page)
                course_info.update(detail_data)

                if detail_data:
                    course_info['스크래핑결과'] = "성공"
                else:
                    course_info['스크래핑결과'] = "파싱 실패"

            except PlaywrightTimeoutError as e:
                print(f"     - 페이지 로딩 시간 초과: {e}")
                course_info['스크래핑결과'] = "타임아웃"
            except Exception as e:
                print(f"     - 스크래핑 중 오류 발생: {e}")
                course_info['스크래핑결과'] = f"오류: {str(e)[:100]}"

            results_list.append(course_info)

            # 진행상황 저장 (10개마다)
            if (index + 1) % 10 == 0:
                temp_df = pd.DataFrame(results_list)
                temp_df.to_csv(r"C:\KOHI\scraped_results_temp.csv", index=False, encoding='utf-8-sig')
                print(f"     - 임시 저장 완료 ({index + 1}개)")

        browser.close()

    # 최종 결과를 CSV로 저장
    if results_list:
        output_df = pd.DataFrame(results_list)
        output_df.to_csv(r"C:\KOHI\scraped_results.csv", index=False, encoding='utf-8-sig')
        print(f"\n✅ 스크래핑 완료!")
        print(f"   - 총 {len(results_list)}개 교육과정 처리")
        print(f"   - 결과 파일: C:\\KOHI\\scraped_results.csv")

        # 성공/실패 통계
        if '스크래핑결과' in output_df.columns:
            success_count = len(output_df[output_df['스크래핑결과'] == '성공'])
            fail_count = len(output_df) - success_count
            print(f"   - 성공: {success_count}개, 실패: {fail_count}개")
    else:
        print("\n❌ 스크래핑할 데이터가 없거나 모든 과정에서 오류가 발생했습니다.")


if __name__ == "__main__":
    run_scraper()