
import pandas as pd
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def parse_detail_page(page):
    """
    상세 페이지의 모든 정보를 파싱하여 하나의 딕셔너리로 반환합니다.
    각 섹션은 개별 try-except 블록으로 감싸 안정성을 높였습니다.
    """
    course_data = {}

    # 1. 교육과정명
    try:
        title_locator = page.locator('h3.sub_cont_title_h3')
        if title_locator.count() > 0:
            course_data['교육과정명'] = title_locator.inner_text(timeout=5000)
    except Exception as e:
        print(f"    - 교육과정명 파싱 오류: {e}")
        course_data['파싱오류_교육과정명'] = str(e)

    # 2. 교육소개
    try:
        intro_header = page.locator("h4:has-text('교육소개')")
        if intro_header.count() > 0:
            # intro_content = intro_header.locator("xpath=./following-sibling::div[1]")
            # course_data['교육소개'] = intro_content.inner_text(timeout=5000)
            
            # 더 정확한 교육소개 내용을 위해, 다음 h4가 나오기 전까지의 p 태그만 가져오도록 수정
            elements = page.locator("h4:has-text('교육소개') ~ p, h4:has-text('교육소개') ~ div.sub_cont_view_cont_wrap > p").all()
            intro_texts = []
            for el in elements:
                # 다음 h4 제목이 나오면 중단
                if el.evaluate("node => node.previousElementSibling && node.previousElementSibling.tagName === 'H4' && node.previousElementSibling.textContent !== '교육소개'"):
                    break
                intro_texts.append(el.inner_text())
            course_data['교육소개'] = "\n".join(intro_texts)

    except Exception as e:
        print(f"    - 교육소개 파싱 오류: {e}")
        course_data['파싱오류_교육소개'] = str(e)

    # 3. 신청정보 (개별 컬럼으로 분리)
    try:
        app_info_header = page.locator("h4:has-text('신청정보')")
        if app_info_header.count() > 0:
            table = app_info_header.locator("xpath=./following-sibling::div[1]//table")
            keys_locs = table.locator("th")
            vals_locs = table.locator("td")
            keys = [k.inner_text(timeout=5000) for k in keys_locs.all()]
            vals = [v.inner_text(timeout=5000) for v in vals_locs.all()]
            
            for i in range(len(keys)):
                key_name = keys[i].strip().replace('/', '_')
                course_data[f'신청_{key_name}'] = vals[i].strip()
    except Exception as e:
        print(f"    - 신청정보 파싱 오류: {e}")
        course_data['파싱오류_신청정보'] = str(e)

    # 4. 수료기준 (개별 컬럼으로 분리)
    try:
        criteria_header = page.locator("h4:has-text('수료기준')")
        if criteria_header.count() > 0:
            table = criteria_header.locator("xpath=./following-sibling::div[1]//table")
            cells = table.locator("td").all()
            for cell in cells:
                key_name = cell.locator("div").inner_text(timeout=5000)
                full_text = cell.inner_text(timeout=5000)
                value = full_text.replace(key_name, '').strip()
                course_data[f'수료기준_{key_name.strip()}'] = value
    except Exception as e:
        print(f"    - 수료기준 파싱 오류: {e}")
        course_data['파싱오류_수료기준'] = str(e)

    # 5. 교육구성 (JSON으로 저장)
    try:
        curriculum_header = page.locator("h4:has-text('교육구성')")
        if curriculum_header.count() > 0:
            table = curriculum_header.locator("xpath=./following-sibling::div[1]//table")
            headers = [th.inner_text(timeout=5000) for th in table.locator("thead th").all()]
            rows = table.locator("tbody tr").all()
            
            curriculum_list = []
            for row in rows:
                cells = [td.inner_text(timeout=5000) for td in row.locator("td").all()]
                row_data = dict(zip(headers, cells))
                curriculum_list.append(row_data)
            
            if curriculum_list:
                course_data['교육구성'] = json.dumps(curriculum_list, ensure_ascii=False)
    except Exception as e:
        print(f"    - 교육구성 파싱 오류: {e}")
        course_data['파싱오류_교육구성'] = str(e)

    # 6. 추천교육과정 (JSON으로 저장)
    try:
        reco_header = page.locator("h4:has-text('추천교육과정')")
        if reco_header.count() > 0:
            table = reco_header.locator("xpath=./following-sibling::div[1]//table")
            if "추천 교육과정이 없습니다" in table.inner_text(timeout=5000):
                course_data['추천교육과정'] = "없음"
            else:
                headers = [th.inner_text(timeout=5000) for th in table.locator("thead th").all()]
                rows = table.locator("tbody tr").all()
                reco_list = []
                for row in rows:
                    cells = [td.inner_text(timeout=5000) for td in row.locator("td").all()]
                    row_data = dict(zip(headers, cells))
                    reco_list.append(row_data)
                if reco_list:
                    course_data['추천교육과정'] = json.dumps(reco_list, ensure_ascii=False)
    except Exception as e:
        print(f"    - 추천교육과정 파싱 오류: {e}")
        course_data['파싱오류_추천교육과정'] = str(e)
        
    return course_data


def run_scraper():
    """
    메인 스크래퍼 함수
    """
    try:
        input_df = pd.read_csv("C:\KOHI\work.csv")
    except FileNotFoundError:
        print("오류: C:\KOHI\work.csv 파일을 찾을 수 없습니다.")
        return

    results_list = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # False로 바꾸면 브라우저가 보임
        page = browser.new_page()

        for index, row in input_df.iterrows():
            course_name = row.iloc[0] # 첫 번째 컬럼을 교육과정명으로 간주
            print(f"[{index + 1}/{len(input_df)}] 스크래핑 시작: {course_name}")
            
            course_info = {'원본_교육과정명': course_name}

            try:
                page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=60000)
                
                # 검색
                page.locator("#planngCrseNm").fill(course_name)
                page.keyboard.press("Enter")
                page.wait_for_selector('.curriculum__box', timeout=10000)

                # 첫 번째 결과 클릭
                first_result_link = page.locator('.curriculum__thumbnail a').first
                if first_result_link.count() == 0:
                    print("    - 검색 결과가 없습니다.")
                    course_info['스크래핑결과'] = "검색 결과 없음"
                    results_list.append(course_info)
                    continue

                # 페이지 이동이 일어나는 클릭이므로, 이동이 완료될 때까지 대기
                with page.expect_navigation(wait_until="networkidle", timeout=60000):
                    first_result_link.click()

                # 상세 정보 파싱
                detail_data = parse_detail_page(page)
                course_info.update(detail_data)

            except PlaywrightTimeoutError:
                print("    - 페이지 로딩 시간 초과.")
                course_info['스크래핑결과'] = "타임아웃"
            except Exception as e:
                print(f"    - 스크래핑 중 오류 발생: {e}")
                course_info['스크래핑결과'] = str(e)
            
            results_list.append(course_info)

        browser.close()

    # 최종 결과를 CSV로 저장
    if results_list:
        output_df = pd.DataFrame(results_list)
        output_df.to_csv("C:\KOHI\scraped_results.csv", index=False, encoding='utf-8-sig')
        print("\n스크래핑 완료! 결과가 C:\KOHI\scraped_results.csv 파일에 저장되었습니다.")
    else:
        print("\n스크래핑할 데이터가 없거나 모든 과정에서 오류가 발생했습니다.")


if __name__ == "__main__":
    run_scraper()
