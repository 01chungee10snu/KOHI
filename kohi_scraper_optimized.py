"""
KOHI 교육과정 스크래퍼 - 검색어 최적화 버전
의미 단위로 분리된 검색어를 사용하여 검색 성공률 극대화
"""

import time
import json
import logging
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_optimized.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class KOHIScraperOptimized:
    def __init__(self):
        self.base_url = "https://edu.kohi.or.kr"
        self.results = []
        self.failed_courses = []

    def search_with_enhanced_terms(self, page, enhanced_terms):
        """개선된 검색어로 검색 수행"""
        try:
            # 검색 페이지로 이동
            page.goto(f"{self.base_url}/index.do")
            page.wait_for_load_state('networkidle')
            time.sleep(2)

            # 검색창 찾기 및 검색어 입력
            search_input = page.locator('#srchWord, input[name="srchWord"]').first
            search_input.click()
            search_input.fill(enhanced_terms)

            logging.info(f"검색어 입력: {enhanced_terms}")

            # 엔터키로 검색
            search_input.press('Enter')

            # 검색 결과 대기
            page.wait_for_load_state('networkidle')
            time.sleep(3)

            # 검색 결과 확인
            results = page.locator('.curriculum__item')
            count = results.count()

            if count == 0:
                # 검색 결과가 없으면 단어를 하나씩 제거하며 재시도
                terms = enhanced_terms.split()
                for i in range(len(terms), 0, -1):
                    retry_terms = ' '.join(terms[:i])
                    logging.info(f"재시도 검색: {retry_terms}")

                    search_input.fill(retry_terms)
                    search_input.press('Enter')
                    page.wait_for_load_state('networkidle')
                    time.sleep(2)

                    results = page.locator('.curriculum__item')
                    count = results.count()
                    if count > 0:
                        logging.info(f"검색 성공 (재시도): {count}개 결과")
                        return True, count

            logging.info(f"검색 결과: {count}개")
            return count > 0, count

        except Exception as e:
            logging.error(f"검색 중 오류: {e}")
            return False, 0

    def extract_course_info(self, page, result_box):
        """교육과정 정보 추출 (검색 결과 + 상세 페이지)"""
        info = {}

        try:
            # 1. 검색 결과 페이지에서 메타데이터 추출
            # 썸네일 이미지
            try:
                thumbnail = result_box.locator('.curriculum__thumbnail img').first
                info['썸네일_이미지'] = thumbnail.get_attribute('src')
            except:
                info['썸네일_이미지'] = ''

            # 교육비 구분
            try:
                price_badge = result_box.locator('.badge--price').first
                info['교육비_구분'] = price_badge.inner_text().strip()
            except:
                info['교육비_구분'] = ''

            # 교육형태
            try:
                type_badge = result_box.locator('.badge--type').first
                info['교육형태'] = type_badge.inner_text().strip()
            except:
                info['교육형태'] = ''

            # 모집상태
            try:
                status_badge = result_box.locator('.badge--status').first
                info['모집상태'] = status_badge.inner_text().strip()
            except:
                info['모집상태'] = ''

            # 교육분야
            try:
                category = result_box.locator('.curriculum__category').first
                info['교육분야'] = category.inner_text().strip()
            except:
                info['교육분야'] = ''

            # 지원플랫폼
            try:
                platform = result_box.locator('.curriculum__platform').first
                info['지원플랫폼'] = platform.inner_text().strip()
            except:
                info['지원플랫폼'] = ''

            # 2. 교육과정명과 코드 추출
            course_title = result_box.locator('.curriculum__title').first
            title_text = course_title.inner_text().strip()
            info['교육과정명'] = title_text

            # onclick 속성에서 코드 추출
            onclick = course_title.get_attribute('onclick')
            if onclick and 'btn_selectPaa0040' in onclick:
                codes = onclick.split("'")
                if len(codes) >= 4:
                    info['교육과정_코드'] = codes[1]
                    info['그룹_코드'] = codes[3]

                    # 3. 상세 페이지로 이동
                    page.evaluate(f"btn_selectPaa0040('{codes[1]}', '{codes[3]}')")
                    page.wait_for_load_state('networkidle')
                    time.sleep(3)

                    # 4. 상세 정보 추출
                    info.update(self.extract_detail_info(page))

            return info

        except Exception as e:
            logging.error(f"정보 추출 중 오류: {e}")
            return info

    def extract_detail_info(self, page):
        """상세 페이지 정보 추출"""
        details = {}

        try:
            # 교육소개
            intro_elem = page.locator('#curri_intro .view-data')
            if intro_elem.count() > 0:
                details['교육소개'] = intro_elem.first.inner_text().strip()

            # 신청정보 테이블
            apply_table = page.locator('.apply-info-table')
            if apply_table.count() > 0:
                rows = apply_table.locator('tr')
                for i in range(rows.count()):
                    row = rows.nth(i)
                    ths = row.locator('th')
                    tds = row.locator('td')

                    for j in range(ths.count()):
                        key = ths.nth(j).inner_text().strip().replace(':', '')
                        value = tds.nth(j).inner_text().strip() if j < tds.count() else ''
                        details[f'신청_{key}'] = value

            # 수료기준 테이블
            completion_table = page.locator('.completion-table')
            if completion_table.count() > 0:
                rows = completion_table.locator('tr')
                for i in range(rows.count()):
                    row = rows.nth(i)
                    ths = row.locator('th')
                    tds = row.locator('td')

                    for j in range(ths.count()):
                        key = ths.nth(j).inner_text().strip().replace(':', '')
                        value = tds.nth(j).inner_text().strip() if j < tds.count() else ''
                        details[f'수료_{key}'] = value

            # 교육구성
            curriculum_section = page.locator('#curriculum_section')
            if curriculum_section.count() > 0:
                curriculum_data = []
                items = curriculum_section.locator('.curriculum-item')
                for i in range(min(items.count(), 10)):
                    item = items.nth(i)
                    item_data = {
                        'title': item.locator('.item-title').inner_text().strip() if item.locator('.item-title').count() > 0 else '',
                        'duration': item.locator('.item-duration').inner_text().strip() if item.locator('.item-duration').count() > 0 else ''
                    }
                    curriculum_data.append(item_data)
                details['교육구성'] = json.dumps(curriculum_data, ensure_ascii=False)

        except Exception as e:
            logging.error(f"상세 정보 추출 중 오류: {e}")

        return details

    def scrape_course(self, course_name, enhanced_terms):
        """단일 교육과정 스크래핑"""
        playwright = sync_playwright().start()
        browser = None

        try:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = context.new_page()

            # 타임아웃 설정
            page.set_default_timeout(30000)

            # 개선된 검색어로 검색
            success, count = self.search_with_enhanced_terms(page, enhanced_terms)

            if not success:
                logging.warning(f"검색 결과 없음: {course_name}")
                return {
                    '원본_교육과정명': course_name,
                    '검색어': enhanced_terms,
                    '스크래핑결과': '검색결과없음',
                    '검색결과수': 0
                }

            # 첫 번째 결과 선택
            results = page.locator('.curriculum__item')
            if results.count() > 0:
                first_result = results.first
                course_info = self.extract_course_info(page, first_result)
                course_info['원본_교육과정명'] = course_name
                course_info['검색어'] = enhanced_terms
                course_info['스크래핑결과'] = '성공'
                course_info['검색결과수'] = count

                return course_info

        except TimeoutError:
            logging.error(f"타임아웃: {course_name}")
            return {
                '원본_교육과정명': course_name,
                '검색어': enhanced_terms,
                '스크래핑결과': '타임아웃',
                '검색결과수': 0
            }

        except Exception as e:
            logging.error(f"스크래핑 실패 - {course_name}: {e}")
            return {
                '원본_교육과정명': course_name,
                '검색어': enhanced_terms,
                '스크래핑결과': f'오류: {str(e)}',
                '검색결과수': 0
            }

        finally:
            if browser:
                browser.close()
            if playwright:
                playwright.stop()

    def run(self, input_file='work_enhanced.csv', output_file='scraped_optimized.csv'):
        """전체 스크래핑 실행"""
        start_time = datetime.now()
        logging.info("=" * 60)
        logging.info("KOHI 교육과정 스크래핑 시작 (최적화 버전)")
        logging.info("=" * 60)

        # 개선된 검색어 파일 로드
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        total_courses = len(df)

        logging.info(f"총 {total_courses}개 교육과정 스크래핑 시작")

        # 각 교육과정 스크래핑
        for idx, row in df.iterrows():
            course_name = row['교육명']
            enhanced_terms = row['검색어_개선']

            logging.info(f"\n[{idx+1}/{total_courses}] 처리중: {course_name}")
            logging.info(f"  검색어: {enhanced_terms}")

            result = self.scrape_course(course_name, enhanced_terms)
            self.results.append(result)

            # 10개마다 임시 저장
            if (idx + 1) % 10 == 0:
                temp_df = pd.DataFrame(self.results)
                temp_df.to_csv('scraped_optimized_temp.csv', index=False, encoding='utf-8-sig')
                logging.info(f"임시 저장 완료: {idx+1}개")

            # 잠시 대기 (서버 부하 방지)
            time.sleep(2)

        # 최종 결과 저장
        final_df = pd.DataFrame(self.results)
        final_df.to_csv(output_file, index=False, encoding='utf-8-sig')

        # 통계 출력
        end_time = datetime.now()
        duration = end_time - start_time

        success_count = sum(1 for r in self.results if r.get('스크래핑결과') == '성공')
        fail_count = total_courses - success_count

        logging.info("\n" + "=" * 60)
        logging.info("스크래핑 완료!")
        logging.info("=" * 60)
        logging.info(f"총 처리: {total_courses}개")
        logging.info(f"성공: {success_count}개 ({success_count/total_courses*100:.1f}%)")
        logging.info(f"실패: {fail_count}개 ({fail_count/total_courses*100:.1f}%)")
        logging.info(f"소요시간: {duration}")
        logging.info(f"결과 파일: {output_file}")

        # 실패 케이스 분석
        if fail_count > 0:
            logging.info("\n실패 케이스 분석:")
            fail_df = final_df[final_df['스크래핑결과'] != '성공']
            fail_reasons = fail_df['스크래핑결과'].value_counts()
            for reason, count in fail_reasons.items():
                logging.info(f"  - {reason}: {count}개")

        return final_df

def main():
    scraper = KOHIScraperOptimized()

    # 샘플 테스트 (처음 10개만)
    test_mode = input("테스트 모드로 실행하시겠습니까? (y/n): ").lower() == 'y'

    if test_mode:
        df = pd.read_csv('work_enhanced.csv', encoding='utf-8-sig')
        test_df = df.head(10)
        test_df.to_csv('work_enhanced_test.csv', index=False, encoding='utf-8-sig')
        scraper.run('work_enhanced_test.csv', 'scraped_optimized_test.csv')
    else:
        scraper.run('work_enhanced.csv', 'scraped_optimized_final.csv')

if __name__ == "__main__":
    main()