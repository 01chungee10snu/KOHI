import pandas as pd
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import time

def parse_detail_page(page):
    """
    상세 페이지의 모든 정보를 파싱하여 하나의 딕셔너리로 반환합니다.
    """
    course_data = {}

    # 1. 교육과정명
    try:
        title_locator = page.locator('h3.sub_cont_title_h3')
        if title_locator.count() > 0:
            course_data['교육과정명'] = title_locator.inner_text(timeout=5000)
    except Exception as e:
        print(f"    - 교육과정명 파싱 오류: {e}")

    # 2. 교육소개
    try:
        intro_header = page.locator("h4:has-text('교육소개')")
        if intro_header.count() > 0:
            # 교육소개 다음 div의 모든 텍스트 내용 가져오기
            intro_content = intro_header.locator("xpath=following-sibling::div[1]")
            if intro_content.count() > 0:
                course_data['교육소개'] = intro_content.inner_text(timeout=5000)
    except Exception as e:
        print(f"    - 교육소개 파싱 오류: {e}")

    # 3. 신청정보 (개별 컬럼으로 분리)
    try:
        app_info_header = page.locator("h4:has-text('신청정보')")
        if app_info_header.count() > 0:
            table = app_info_header.locator("xpath=following-sibling::div[1]//table")
            if table.count() > 0:
                rows = table.locator("tr").all()
                for row in rows:
                    th = row.locator("th")
                    td = row.locator("td")
                    if th.count() > 0 and td.count() > 0:
                        keys = [k.inner_text() for k in th.all()]
                        vals = [v.inner_text() for v in td.all()]
                        for i in range(len(keys)):
                            if i < len(vals):
                                key_name = keys[i].strip().replace('/', '_').replace(' ', '_')
                                course_data[f'신청_{key_name}'] = vals[i].strip()
    except Exception as e:
        print(f"    - 신청정보 파싱 오류: {e}")

    # 4. 수료기준
    try:
        criteria_header = page.locator("h4:has-text('수료기준')")
        if criteria_header.count() > 0:
            criteria_content = criteria_header.locator("xpath=following-sibling::div[1]")
            if criteria_content.count() > 0:
                # 테이블이 있는 경우
                table = criteria_content.locator("table")
                if table.count() > 0:
                    cells = table.locator("td").all()
                    for cell in cells:
                        cell_text = cell.inner_text()
                        # 셀 내용을 파싱 (예: "진도율 90% 이상")
                        parts = cell_text.strip().split('\n')
                        if len(parts) >= 2:
                            key = parts[0].strip()
                            value = ' '.join(parts[1:]).strip()
                            course_data[f'수료기준_{key}'] = value
                        else:
                            course_data['수료기준'] = cell_text
                else:
                    # 테이블이 없으면 전체 텍스트
                    course_data['수료기준'] = criteria_content.inner_text()
    except Exception as e:
        print(f"    - 수료기준 파싱 오류: {e}")

    # 5. 교육구성
    try:
        curriculum_header = page.locator("h4:has-text('교육구성')")
        if curriculum_header.count() > 0:
            table = curriculum_header.locator("xpath=following-sibling::div[1]//table")
            if table.count() > 0:
                headers = [th.inner_text() for th in table.locator("thead th").all()]
                rows = table.locator("tbody tr").all()

                curriculum_list = []
                for row in rows:
                    cells = [td.inner_text() for td in row.locator("td").all()]
                    if headers and cells:
                        row_data = dict(zip(headers, cells))
                        curriculum_list.append(row_data)

                if curriculum_list:
                    course_data['교육구성'] = json.dumps(curriculum_list, ensure_ascii=False)
    except Exception as e:
        print(f"    - 교육구성 파싱 오류: {e}")

    # 6. 추천교육과정
    try:
        reco_header = page.locator("h4:has-text('추천교육과정')")
        if reco_header.count() > 0:
            table = reco_header.locator("xpath=following-sibling::div[1]//table")
            if table.count() > 0:
                table_text = table.inner_text()
                if "추천 교육과정이 없습니다" in table_text:
                    course_data['추천교육과정'] = "없음"
                else:
                    headers = [th.inner_text() for th in table.locator("thead th").all()]
                    rows = table.locator("tbody tr").all()
                    reco_list = []
                    for row in rows:
                        cells = [td.inner_text() for td in row.locator("td").all()]
                        if headers and cells:
                            row_data = dict(zip(headers, cells))
                            reco_list.append(row_data)
                    if reco_list:
                        course_data['추천교육과정'] = json.dumps(reco_list, ensure_ascii=False)
    except Exception as e:
        print(f"    - 추천교육과정 파싱 오류: {e}")

    return course_data


def test_single_course():
    """
    단일 교육과정으로 테스트
    """
    test_course = "긴급복지지원 신고의무 교육"
    print(f"테스트 교육과정: {test_course}")

    with sync_playwright() as p:
        # headless=False로 브라우저 보이기
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        course_info = {'원본_교육과정명': test_course}

        try:
            # 1. 메인 페이지 이동
            print("1. 메인 페이지 로딩...")
            page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=60000)
            page.wait_for_load_state("networkidle")

            # 2. 검색
            print("2. 교육과정 검색...")
            search_input = page.locator("#planngCrseNm")
            search_input.fill(test_course)
            page.keyboard.press("Enter")

            # 검색 결과 대기
            page.wait_for_selector('.curriculum__box', timeout=10000)
            time.sleep(2)  # 결과 로딩 대기

            # 3. 검색 결과 확인
            print("3. 검색 결과 확인...")
            results = page.locator('.curriculum__box').all()
            print(f"   - 검색 결과 수: {len(results)}")

            if len(results) == 0:
                print("   - 검색 결과가 없습니다.")
                course_info['스크래핑결과'] = "검색 결과 없음"
                return course_info

            # 첫 번째 결과의 제목 확인
            first_title = page.locator('.curriculum__info--title').first.inner_text()
            print(f"   - 첫 번째 결과: {first_title}")

            # 4. 상세 페이지로 이동
            print("4. 상세 페이지 이동...")
            thumbnail_link = page.locator('.curriculum__thumbnail a').first

            # 클릭 전 URL 저장
            current_url = page.url

            # 클릭
            thumbnail_link.click()

            # 페이지 이동 대기
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # URL 변경 확인
            new_url = page.url
            if current_url != new_url:
                print(f"   - 페이지 이동 성공: {new_url}")
            else:
                print("   - 페이지 이동 실패 (같은 URL)")

            # 5. 상세 정보 파싱
            print("5. 상세 정보 파싱...")
            detail_data = parse_detail_page(page)
            course_info.update(detail_data)

            # 결과 출력
            print("\n=== 파싱 결과 ===")
            for key, value in course_info.items():
                if isinstance(value, str) and len(value) > 100:
                    print(f"{key}: {value[:100]}...")
                else:
                    print(f"{key}: {value}")

        except PlaywrightTimeoutError as e:
            print(f"   - 페이지 로딩 시간 초과: {e}")
            course_info['스크래핑결과'] = "타임아웃"
        except Exception as e:
            print(f"   - 스크래핑 중 오류 발생: {e}")
            course_info['스크래핑결과'] = str(e)
        finally:
            input("\n브라우저를 닫으려면 Enter를 누르세요...")
            browser.close()

    return course_info


if __name__ == "__main__":
    result = test_single_course()

    # 결과를 CSV로 저장
    df = pd.DataFrame([result])
    df.to_csv(r"C:\KOHI\test_result.csv", index=False, encoding='utf-8-sig')
    print(f"\n결과가 C:\\KOHI\\test_result.csv에 저장되었습니다.")