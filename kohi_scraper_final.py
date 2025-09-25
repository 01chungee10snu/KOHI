import pandas as pd
import json
from playwright.sync_api import sync_playwright
import time
import logging
from datetime import datetime
import os

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_final.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clean_text(text):
    """텍스트 정제"""
    if not text:
        return ""
    return ' '.join(text.split()).strip()

def extract_table_data_as_dict(table):
    """테이블을 딕셔너리로 변환"""
    data = {}
    try:
        rows = table.locator("tr").all()
        for row in rows:
            ths = row.locator("th").all()
            tds = row.locator("td").all()

            # th-td 쌍 처리
            for i in range(len(ths)):
                if i < len(tds):
                    key = clean_text(ths[i].inner_text())
                    value = clean_text(tds[i].inner_text())
                    if key:
                        data[key] = value
    except Exception as e:
        logger.error(f"테이블 파싱 오류: {e}")
    return data

def extract_table_data_as_list(table):
    """테이블을 리스트로 변환 (헤더 있는 경우)"""
    data = []
    try:
        # 헤더 추출
        headers = []
        thead = table.locator("thead")
        if thead.count() > 0:
            headers = [clean_text(th.inner_text()) for th in thead.locator("th").all()]
        else:
            # thead가 없으면 첫 번째 tr에서 th 찾기
            first_row = table.locator("tr").first
            if first_row.count() > 0:
                ths = first_row.locator("th").all()
                if ths:
                    headers = [clean_text(th.inner_text()) for th in ths]

        if headers:
            # 데이터 행 추출
            tbody = table.locator("tbody")
            if tbody.count() > 0:
                rows = tbody.locator("tr").all()
            else:
                # tbody가 없으면 헤더 다음 행부터
                all_rows = table.locator("tr").all()
                rows = all_rows[1:] if len(all_rows) > 1 else []

            for row in rows:
                cells = [clean_text(td.inner_text()) for td in row.locator("td").all()]
                if cells and len(cells) == len(headers):
                    data.append(dict(zip(headers, cells)))
    except Exception as e:
        logger.error(f"테이블 리스트 파싱 오류: {e}")
    return data

def scrape_course(course_name, playwright_instance):
    """단일 교육과정 스크래핑"""
    result = {
        '원본_교육과정명': course_name,
        '스크래핑_시각': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    browser = None
    try:
        # 새 브라우저 인스턴스 생성
        browser = playwright_instance.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        page = browser.new_page()

        # 1. 메인 페이지 이동
        logger.info(f"  검색 페이지 로딩...")
        page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=10000)

        # 2. 검색어 입력 및 검색
        logger.info(f"  검색어 입력: {course_name}")
        search_input = page.locator("#planngCrseNm")
        search_input.fill(course_name)

        # Enter 키로 검색
        page.keyboard.press("Enter")

        # 검색 결과 대기 (AJAX 완료 대기)
        time.sleep(3)

        try:
            page.wait_for_selector(".curriculum__box", timeout=5000)
        except:
            logger.warning("  검색 결과 대기 시간 초과")

        # 3. 검색 결과 확인
        results = page.locator(".curriculum__box").all()
        logger.info(f"  검색 결과: {len(results)}개")

        if len(results) == 0:
            result['스크래핑결과'] = '검색 결과 없음'
            return result

        # 첫 번째 결과 정보 수집
        first_result = results[0]

        # 검색 결과 제목
        title_elem = first_result.locator(".curriculum__info--title")
        if title_elem.count() > 0:
            result['검색결과_제목'] = clean_text(title_elem.inner_text())
            logger.info(f"  찾은 교육과정: {result['검색결과_제목']}")

        # 4. 상세 페이지로 이동
        # 썸네일 링크 또는 수강신청 버튼 찾기
        detail_link = first_result.locator("a").first

        if detail_link.count() > 0:
            # 새 페이지에서 열릴 수 있으므로 대기
            with page.expect_navigation(timeout=30000, wait_until="domcontentloaded"):
                detail_link.click()

            time.sleep(2)  # 페이지 완전 로딩 대기

            # URL 확인
            current_url = page.url
            logger.info(f"  상세 페이지 URL: {current_url}")

            # 5. 상세 페이지 파싱
            result['상세페이지_URL'] = current_url

            # 교육과정명
            for selector in ['h3.tit', 'h3.sub_cont_title_h3', 'h3']:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    title = clean_text(elem.inner_text())
                    if title and len(title) > 2 and '교육' not in selector:
                        result['교육과정명'] = title
                        break

            # 모든 테이블 분석
            tables = page.locator("table").all()
            logger.info(f"  테이블 수: {len(tables)}")

            for idx, table in enumerate(tables):
                try:
                    table_text = table.inner_text()

                    # 신청정보 테이블
                    if any(key in table_text for key in ['교육대상', '신청기간', '교육기간']):
                        logger.info(f"    신청정보 테이블 발견")
                        table_data = extract_table_data_as_dict(table)
                        for key, value in table_data.items():
                            result[f'신청_{key}'] = value

                    # 수료기준 테이블
                    elif '수료' in table_text and any(key in table_text for key in ['출석', '시험', '과제']):
                        logger.info(f"    수료기준 테이블 발견")
                        # 첫 행이 헤더, 두 번째 행이 데이터인 경우
                        rows = table.locator("tr").all()
                        if len(rows) >= 2:
                            headers = [clean_text(th.inner_text()) for th in rows[0].locator("th").all()]
                            values = [clean_text(td.inner_text()) for td in rows[1].locator("td").all()]

                            if len(headers) == len(values):
                                for h, v in zip(headers, values):
                                    if h:
                                        result[f'수료_{h}'] = v

                    # 교육구성 테이블
                    elif any(key in table_text for key in ['교과목', '강사', '교육일']):
                        logger.info(f"    교육구성 테이블 발견")
                        curriculum_data = extract_table_data_as_list(table)
                        if curriculum_data:
                            result['교육구성'] = json.dumps(curriculum_data, ensure_ascii=False)
                            result['교육구성_과목수'] = len(curriculum_data)

                    # 추천교육과정 테이블
                    elif '추천' in table_text:
                        logger.info(f"    추천교육과정 테이블 발견")
                        if '추천 교육과정이 없습니다' in table_text:
                            result['추천교육과정'] = '없음'
                        else:
                            reco_data = extract_table_data_as_list(table)
                            if reco_data:
                                result['추천교육과정'] = json.dumps(reco_data, ensure_ascii=False)
                                result['추천교육과정_수'] = len(reco_data)

                except Exception as e:
                    logger.error(f"    테이블 {idx} 파싱 오류: {e}")

            # 교육소개 섹션
            for selector in ['#introduction', 'div:has(> h4:text("교육소개"))']:
                elem = page.locator(selector).first
                if elem.count() > 0:
                    intro_text = clean_text(elem.inner_text())
                    if intro_text:
                        # '교육소개' 헤더 제거
                        intro_text = intro_text.replace('교육소개', '', 1).strip()
                        if intro_text:
                            result['교육소개'] = intro_text[:500]  # 최대 500자
                            break

            # 성공 여부 판단
            parsed_fields = len([k for k in result.keys() if k not in ['원본_교육과정명', '스크래핑_시각', '상세페이지_URL']])

            if parsed_fields > 3:
                result['스크래핑결과'] = '성공'
            else:
                result['스크래핑결과'] = '부분 성공'

            logger.info(f"  파싱 필드 수: {parsed_fields}")
        else:
            result['스크래핑결과'] = '상세 링크 없음'

    except Exception as e:
        logger.error(f"  스크래핑 오류: {e}")
        result['스크래핑결과'] = f'오류: {str(e)[:100]}'

    finally:
        if browser:
            browser.close()

    return result

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

    results = []

    with sync_playwright() as p:
        for idx, course_name in enumerate(course_names, 1):
            logger.info(f"\n[{idx}/{len(course_names)}] {course_name}")

            # 각 교육과정 스크래핑
            result = scrape_course(course_name, p)
            results.append(result)

            # 진행상황 저장 (10개마다)
            if idx % 10 == 0:
                temp_df = pd.DataFrame(results)
                temp_df.to_csv(r"C:\KOHI\scraped_temp.csv", index=False, encoding='utf-8-sig')
                logger.info(f"임시 저장: {idx}개 완료")

            # 속도 조절 (서버 부하 방지)
            if idx < len(course_names):
                time.sleep(1)

    # 최종 결과 저장
    if results:
        final_df = pd.DataFrame(results)
        final_df.to_csv(r"C:\KOHI\scraped_final.csv", index=False, encoding='utf-8-sig')

        # 통계 출력
        logger.info("\n" + "="*50)
        logger.info("스크래핑 완료!")
        logger.info(f"총 처리: {len(results)}개")

        if '스크래핑결과' in final_df.columns:
            stats = final_df['스크래핑결과'].value_counts()
            for status, count in stats.items():
                logger.info(f"  {status}: {count}개")

        # 수집된 필드 통계
        field_counts = {}
        for col in final_df.columns:
            non_null = final_df[col].notna().sum()
            if non_null > 0:
                field_counts[col] = non_null

        logger.info("\n주요 수집 필드:")
        for field, count in sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
            logger.info(f"  {field}: {count}개")

        logger.info(f"\n최종 결과 파일: C:\\KOHI\\scraped_final.csv")

if __name__ == "__main__":
    main()