import pandas as pd
import json
from playwright.sync_api import sync_playwright
import time
import logging
from datetime import datetime
import os
import re

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_ultimate.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clean_text(text):
    """텍스트 정제"""
    if not text:
        return ""
    return ' '.join(text.split()).strip()

def safe_get_text(element, default=""):
    """안전하게 요소의 텍스트 가져오기"""
    try:
        if element and element.count() > 0:
            return clean_text(element.inner_text())
    except:
        pass
    return default

def safe_get_attribute(element, attr, default=""):
    """안전하게 요소의 속성 가져오기"""
    try:
        if element and element.count() > 0:
            return element.get_attribute(attr)
    except:
        pass
    return default

def extract_search_result_info(result_box, page):
    """검색 결과 페이지의 각 교육과정 박스에서 모든 정보 추출"""
    info = {}

    try:
        # 1. 썸네일 이미지 URL
        thumbnail = result_box.locator('.curriculum__thumbnail img').first
        if thumbnail.count() > 0:
            img_src = thumbnail.get_attribute('src')
            if img_src and not img_src.endswith('no_img.gif'):
                info['썸네일_이미지'] = img_src

        # 2. 교육비 유료/무료
        charge_elem = result_box.locator('.change-ico-box .ico').first
        if charge_elem.count() > 0:
            charge_text = charge_elem.inner_text()
            info['교육비_구분'] = charge_text

        # 3. 교육형태 배지 (대면/온라인 등)
        badge = result_box.locator('.curriculum__info--badge .badge').first
        if badge.count() > 0:
            badge_class = badge.get_attribute('class')
            badge_text = badge.inner_text()
            info['교육형태'] = badge_text

            # 클래스명으로 더 정확한 구분
            if 'face' in badge_class:
                info['교육형태_구분'] = '대면'
            elif 'live' in badge_class:
                info['교육형태_구분'] = '라이브'
            elif 'hybrid' in badge_class:
                info['교육형태_구분'] = '하이브리드'
            elif 'e-learning' in badge_class:
                info['교육형태_구분'] = '이러닝'
            elif 'bl' in badge_class:
                info['교육형태_구분'] = 'B/L'

        # 4. 교육분야 카테고리
        category_spans = result_box.locator('.curriculum__info--badge span').all()
        categories = []
        for span in category_spans:
            text = clean_text(span.inner_text())
            if text and not text.startswith('모집'):
                categories.append(text)
        if categories:
            info['교육분야'] = ', '.join(categories)

        # 5. 모집상태
        recruit_status = result_box.locator('.curriculum__info--badge em').first
        if recruit_status.count() > 0:
            status_class = recruit_status.get_attribute('class')
            status_text = recruit_status.inner_text()
            info['모집상태'] = status_text

            if 'yellow' in status_class:
                info['모집상태_구분'] = '진행중'
            elif 'gray' in status_class:
                info['모집상태_구분'] = '마감'

        # 6. 교육대상
        target_elem = result_box.locator('.curriculum__info--badge em.gray').first
        if target_elem.count() > 0:
            target_text = target_elem.inner_text()
            if '공무원' in target_text or '민간' in target_text:
                info['교육대상_표시'] = target_text

        # 7. 플랫폼 호환성
        pc_elem = result_box.locator('.info--pc')
        mobile_elem = result_box.locator('.info--mobile')
        sign_elem = result_box.locator('.info--sign')

        platforms = []
        if pc_elem.count() > 0:
            platforms.append('PC')
        if mobile_elem.count() > 0:
            platforms.append('Mobile')
        if sign_elem.count() > 0:
            platforms.append('수어지원')

        if platforms:
            info['지원플랫폼'] = ', '.join(platforms)

        # 8. 맛보기 영상 링크
        teaser = result_box.locator('.slide__link--teaser').first
        if teaser.count() > 0:
            info['맛보기영상'] = '있음'

        # 9. 상세 정보 텍스트들
        details = result_box.locator('.curriculum__info--detail p').all()
        for detail in details:
            text = detail.inner_text()
            if '신청기간' in text:
                info['검색결과_신청기간'] = text.replace('신청기간 : ', '').strip()
            elif '교육기간' in text:
                info['검색결과_교육기간'] = text.replace('교육기간 : ', '').strip()
            elif '교육시간' in text:
                info['검색결과_교육시간'] = text.replace('교육시간 : ', '').strip()
            elif '신청인원' in text:
                info['검색결과_신청현황'] = text.replace('신청인원/정원 : ', '').strip()

        # 10. onclick 속성에서 코드 추출
        link = result_box.locator('a').first
        if link.count() > 0:
            onclick = link.get_attribute('onclick')
            if onclick:
                match = re.search(r"btn_selectPaa0040\('([^']+)','([^']+)'\)", onclick)
                if match:
                    info['교육과정코드'] = match.group(1)
                    info['교육그룹코드'] = match.group(2)

    except Exception as e:
        logger.error(f"검색 결과 정보 추출 오류: {e}")

    return info

def extract_detail_page_complete(page):
    """상세 페이지에서 모든 정보 완전 추출"""
    data = {}

    try:
        # 현재 URL 저장
        data['상세페이지_URL'] = page.url

        # 1. 페이지 제목 (다양한 selector 시도)
        title_selectors = [
            'h3.tit',
            'h3.sub_cont_title_h3',
            '.page-title h3',
            '.content-title',
            'h3'
        ]

        for selector in title_selectors:
            elem = page.locator(selector).first
            if elem.count() > 0:
                title = clean_text(elem.inner_text())
                if title and len(title) > 2:
                    data['교육과정명'] = title
                    break

        # 2. 모든 h4 섹션 찾기 (교육소개, 교육목표 등)
        h4_sections = page.locator('h4').all()
        for h4 in h4_sections:
            try:
                section_title = clean_text(h4.inner_text())

                # 다음 형제 요소들에서 내용 수집
                content = page.evaluate(f"""
                    (() => {{
                        const h4 = Array.from(document.querySelectorAll('h4')).find(el => el.textContent.includes('{section_title}'));
                        if (!h4) return '';
                        let content = '';
                        let next = h4.nextElementSibling;
                        while (next && next.tagName !== 'H4') {{
                            if (next.tagName !== 'SCRIPT' && next.tagName !== 'STYLE') {{
                                content += next.innerText + ' ';
                            }}
                            next = next.nextElementSibling;
                        }}
                        return content.trim();
                    }})()
                """)

                if content:
                    # 섹션별로 저장
                    if '교육소개' in section_title:
                        data['교육소개'] = clean_text(content)
                    elif '교육목표' in section_title:
                        data['교육목표'] = clean_text(content)
                    elif '학습방법' in section_title:
                        data['학습방법'] = clean_text(content)
                    elif '평가방법' in section_title:
                        data['평가방법'] = clean_text(content)
                    elif '강사' in section_title:
                        data['강사정보'] = clean_text(content)
                    elif '문의' in section_title:
                        data['문의처'] = clean_text(content)
                    else:
                        # 기타 섹션
                        data[f'기타_{section_title}'] = clean_text(content)[:500]

            except Exception as e:
                logger.debug(f"h4 섹션 파싱 오류: {e}")

        # 3. 모든 테이블 분석 (더 정밀하게)
        tables = page.locator('table').all()
        logger.info(f"  테이블 수: {len(tables)}")

        for idx, table in enumerate(tables):
            try:
                table_html = table.inner_html()
                table_text = table.inner_text()

                # 신청정보 테이블
                if any(key in table_text for key in ['교육대상', '신청기간', '교육기간', '교육비']):
                    rows = table.locator('tr').all()
                    for row in rows:
                        ths = row.locator('th').all()
                        tds = row.locator('td').all()

                        for i in range(len(ths)):
                            if i < len(tds):
                                key = clean_text(ths[i].inner_text())
                                value = clean_text(tds[i].inner_text())
                                if key:
                                    # 키 이름 정규화
                                    key_normalized = key.replace('/', '_').replace(' ', '_')
                                    data[f'신청_{key_normalized}'] = value

                # 수료기준 테이블
                elif any(key in table_text for key in ['수료', '출석', '시험', '과제']):
                    # 테이블 구조에 따라 다르게 처리
                    rows = table.locator('tr').all()

                    # 헤더가 있는 경우
                    if len(rows) >= 2:
                        headers = []
                        for th in rows[0].locator('th, td').all():
                            headers.append(clean_text(th.inner_text()))

                        # 데이터 행
                        if len(rows) > 1:
                            values = []
                            for td in rows[1].locator('td').all():
                                values.append(clean_text(td.inner_text()))

                            if len(headers) == len(values):
                                for h, v in zip(headers, values):
                                    if h:
                                        data[f'수료_{h}'] = v

                # 교육구성 테이블
                elif any(key in table_text for key in ['교과목', '강사', '교육일', '차시']):
                    # 헤더 찾기
                    headers = []
                    thead = table.locator('thead')
                    if thead.count() > 0:
                        headers = [clean_text(th.inner_text()) for th in thead.locator('th').all()]
                    else:
                        first_row = table.locator('tr').first
                        if first_row.count() > 0:
                            headers = [clean_text(th.inner_text()) for th in first_row.locator('th').all()]

                    if headers:
                        # 데이터 행 수집
                        tbody = table.locator('tbody')
                        if tbody.count() > 0:
                            data_rows = tbody.locator('tr').all()
                        else:
                            all_rows = table.locator('tr').all()
                            data_rows = all_rows[1:] if len(all_rows) > 1 else []

                        curriculum_data = []
                        for row in data_rows:
                            cells = [clean_text(td.inner_text()) for td in row.locator('td').all()]
                            if cells and len(cells) == len(headers):
                                curriculum_data.append(dict(zip(headers, cells)))

                        if curriculum_data:
                            data['교육구성'] = json.dumps(curriculum_data, ensure_ascii=False)
                            data['교육구성_과목수'] = len(curriculum_data)

                            # 총 교육시간 계산 시도
                            total_hours = 0
                            for item in curriculum_data:
                                for key in ['시간', '교육시간', '차시']:
                                    if key in item:
                                        try:
                                            # 숫자만 추출
                                            hours = re.findall(r'\d+\.?\d*', item[key])
                                            if hours:
                                                total_hours += float(hours[0])
                                        except:
                                            pass
                            if total_hours > 0:
                                data['교육구성_총시간'] = total_hours

                # 추천교육과정 테이블
                elif '추천' in table_text:
                    if '추천 교육과정이 없습니다' in table_text:
                        data['추천교육과정'] = '없음'
                    else:
                        # 추천 과정 파싱
                        headers = []
                        thead = table.locator('thead')
                        if thead.count() > 0:
                            headers = [clean_text(th.inner_text()) for th in thead.locator('th').all()]

                        if headers:
                            tbody = table.locator('tbody')
                            if tbody.count() > 0:
                                reco_data = []
                                for row in tbody.locator('tr').all():
                                    cells = [clean_text(td.inner_text()) for td in row.locator('td').all()]
                                    if cells and len(cells) == len(headers):
                                        reco_data.append(dict(zip(headers, cells)))

                                if reco_data:
                                    data['추천교육과정'] = json.dumps(reco_data, ensure_ascii=False)
                                    data['추천교육과정_수'] = len(reco_data)

                # 기타 정보 테이블
                else:
                    # 테이블에 유용한 정보가 있는지 확인
                    if len(table_text) > 20 and len(table_text) < 2000:
                        # th-td 쌍으로 이루어진 정보성 테이블
                        rows = table.locator('tr').all()
                        for row in rows:
                            ths = row.locator('th').all()
                            tds = row.locator('td').all()

                            for i in range(len(ths)):
                                if i < len(tds):
                                    key = clean_text(ths[i].inner_text())
                                    value = clean_text(tds[i].inner_text())
                                    if key and value and len(key) < 30:
                                        data[f'기타정보_{key}'] = value[:200]

            except Exception as e:
                logger.debug(f"테이블 {idx} 파싱 오류: {e}")

        # 4. 다운로드 가능한 파일 확인
        download_links = page.locator('a[href*="download"], a[href*="file"]').all()
        if download_links:
            downloads = []
            for link in download_links[:5]:  # 최대 5개만
                href = link.get_attribute('href')
                text = clean_text(link.inner_text())
                if href and text:
                    downloads.append(f"{text}: {href}")
            if downloads:
                data['다운로드_자료'] = ', '.join(downloads)

        # 5. 메타 정보 수집 (있다면)
        meta_info = page.locator('meta[property*="og:"], meta[name*="description"]').all()
        for meta in meta_info:
            prop = meta.get_attribute('property') or meta.get_attribute('name')
            content = meta.get_attribute('content')
            if prop and content:
                if 'description' in prop:
                    data['메타_설명'] = content[:200]
                elif 'image' in prop:
                    data['메타_이미지'] = content

    except Exception as e:
        logger.error(f"상세 페이지 전체 파싱 오류: {e}")
        data['파싱오류'] = str(e)[:200]

    return data

def scrape_course_complete(course_name, playwright_instance):
    """단일 교육과정 완전 스크래핑"""
    result = {
        '원본_교육과정명': course_name,
        '스크래핑_시각': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    browser = None
    try:
        # 브라우저 시작
        browser = playwright_instance.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        page = browser.new_page()

        # 1. 검색 페이지 이동
        logger.info(f"  검색 시작: {course_name}")
        page.goto("https://edu.kohi.or.kr/pt/pa/paa/BD_paa0010l.do", timeout=30000)
        page.wait_for_load_state("networkidle", timeout=10000)

        # 2. 검색 실행
        search_input = page.locator("#planngCrseNm")
        search_input.fill(course_name)
        page.keyboard.press("Enter")

        # 검색 결과 대기
        time.sleep(3)

        try:
            page.wait_for_selector(".curriculum__box", timeout=5000)
        except:
            logger.debug("  검색 결과 대기 시간 초과")

        # 3. 검색 결과 분석
        results = page.locator(".curriculum__box").all()
        logger.info(f"  검색 결과: {len(results)}개")

        if len(results) == 0:
            result['스크래핑결과'] = '검색 결과 없음'
            return result

        # 첫 번째 결과에서 정보 추출
        first_result = results[0]

        # 검색 결과 페이지에서 모든 정보 추출
        search_info = extract_search_result_info(first_result, page)
        result.update(search_info)

        # 기본 제목 수집
        title_elem = first_result.locator(".curriculum__info--title")
        if title_elem.count() > 0:
            result['검색결과_제목'] = clean_text(title_elem.inner_text())

        # 4. 상세 페이지로 이동
        detail_link = first_result.locator("a").first

        if detail_link.count() > 0:
            # 새 페이지에서 열릴 수 있으므로 대기
            try:
                with page.expect_navigation(timeout=30000, wait_until="domcontentloaded"):
                    detail_link.click()
            except:
                # navigation이 없을 경우 그냥 클릭
                detail_link.click()
                page.wait_for_load_state("domcontentloaded")

            time.sleep(2)  # 페이지 완전 로딩 대기

            # URL 확인
            current_url = page.url
            logger.info(f"  상세 페이지 이동: {current_url}")

            # 5. 상세 페이지에서 완전한 정보 추출
            detail_data = extract_detail_page_complete(page)
            result.update(detail_data)

            # 성공 여부 판단
            parsed_fields = len([k for k in result.keys()
                               if k not in ['원본_교육과정명', '스크래핑_시각']])

            if parsed_fields > 10:
                result['스크래핑결과'] = '성공'
                result['수집_필드수'] = parsed_fields
            elif parsed_fields > 5:
                result['스크래핑결과'] = '부분 성공'
                result['수집_필드수'] = parsed_fields
            else:
                result['스크래핑결과'] = '정보 부족'
                result['수집_필드수'] = parsed_fields

            logger.info(f"  수집 완료: {parsed_fields}개 필드")
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

            # 각 교육과정 완전 스크래핑
            result = scrape_course_complete(course_name, p)
            results.append(result)

            # 진행상황 저장 (10개마다)
            if idx % 10 == 0:
                temp_df = pd.DataFrame(results)
                temp_df.to_csv(r"C:\KOHI\scraped_ultimate_temp.csv", index=False, encoding='utf-8-sig')
                logger.info(f"임시 저장: {idx}개 완료")

            # 속도 조절 (서버 부하 방지)
            if idx < len(course_names):
                time.sleep(1)

    # 최종 결과 저장
    if results:
        final_df = pd.DataFrame(results)
        final_df.to_csv(r"C:\KOHI\scraped_ultimate_final.csv", index=False, encoding='utf-8-sig')

        # 통계 출력
        logger.info("\n" + "="*50)
        logger.info("🎉 완벽한 스크래핑 완료!")
        logger.info(f"총 처리: {len(results)}개")

        if '스크래핑결과' in final_df.columns:
            stats = final_df['스크래핑결과'].value_counts()
            for status, count in stats.items():
                logger.info(f"  {status}: {count}개")

        # 수집된 필드 통계
        all_columns = set(final_df.columns)
        logger.info(f"\n총 수집 필드 종류: {len(all_columns)}개")

        # 주요 필드별 수집률
        field_counts = {}
        for col in final_df.columns:
            non_null = final_df[col].notna().sum()
            if non_null > 0:
                field_counts[col] = non_null

        logger.info("\n📊 주요 수집 필드 (상위 20개):")
        for field, count in sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
            percentage = (count / len(results)) * 100
            logger.info(f"  {field}: {count}개 ({percentage:.1f}%)")

        # 새로 추가된 필드 강조
        new_fields = [col for col in all_columns if any(keyword in col for keyword in
                     ['썸네일', '교육형태', '모집상태', '교육비_구분', '플랫폼', '교육목표',
                      '학습방법', '평가방법', '강사', '교육분야', '맛보기'])]

        if new_fields:
            logger.info(f"\n✨ 새로 추가된 주요 필드:")
            for field in new_fields:
                count = final_df[field].notna().sum()
                if count > 0:
                    logger.info(f"  {field}: {count}개")

        logger.info(f"\n💾 최종 결과 파일: C:\\KOHI\\scraped_ultimate_final.csv")

if __name__ == "__main__":
    main()