"""
최적화 스크래퍼 테스트
10개 샘플로 개선 효과 검증
"""

import pandas as pd
import logging
from kohi_scraper_optimized import KOHIScraperOptimized

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test_optimized_scraper():
    """최적화 스크래퍼 테스트"""

    print("\n" + "="*70)
    print(" "*25 + "최적화 스크래퍼 테스트")
    print("="*70)

    # 테스트용 샘플 데이터 준비
    df = pd.read_csv('work_enhanced.csv', encoding='utf-8-sig')

    # 다양한 케이스 선택 (개선율이 다른 10개)
    test_indices = [
        0,   # 긴급복지지원 (1.3x)
        6,   # 보건복지인을위한문제해결 (4.0x)
        21,  # KOHI북토크 (4.0x)
        17,  # 창의적인정책개발 (3.0x)
        40,  # 국민기초생활보장제도 (2.5x)
        56,  # 사회복지시설안전관리 (2.0x)
        73,  # 장애와인권 (2.0x)
        85,  # 신설아동보호전문기관 (1.0x)
        115, # 중대재해처벌법 (1.0x)
        153  # 비만의 민족 (1.0x)
    ]

    test_df = df.iloc[test_indices]
    test_df.to_csv('work_enhanced_test.csv', index=False, encoding='utf-8-sig')

    print(f"\n[테스트 데이터]")
    print("-"*70)
    for idx, row in test_df.iterrows():
        print(f"{idx+1}. {row['교육명'][:30]:30s} | 개선율: {row['개선율']:.1f}x")
        print(f"   AS-IS: {row['검색어_원본'][:50]}")
        print(f"   TO-BE: {row['검색어_개선'][:50]}")
        print()

    # 스크래퍼 실행
    print("\n스크래핑 시작...")
    print("-"*70)

    scraper = KOHIScraperOptimized()
    result_df = scraper.run('work_enhanced_test.csv', 'scraped_optimized_test.csv')

    # 결과 분석
    print("\n" + "="*70)
    print(" "*25 + "테스트 결과 분석")
    print("="*70)

    success_count = len(result_df[result_df['스크래핑결과'] == '성공'])
    total_count = len(result_df)

    print(f"\n성공률: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")

    # 개선 효과 분석
    print("\n[개선 효과 분석]")
    print("-"*70)

    for idx, row in result_df.iterrows():
        original_name = row['원본_교육과정명']
        search_terms = row['검색어']
        result = row['스크래핑결과']
        count = row.get('검색결과수', 0)

        status = "✓" if result == '성공' else "✗"
        print(f"{status} {original_name[:30]:30s}")
        print(f"  검색어: {search_terms[:50]}")
        print(f"  결과: {result} (검색결과 {count}개)")
        print()

    # 수집된 필드 분석
    if success_count > 0:
        success_rows = result_df[result_df['스크래핑결과'] == '성공']
        field_counts = success_rows.notna().sum()

        print("\n[수집 필드 통계]")
        print("-"*70)
        print(f"평균 수집 필드: {field_counts.mean():.1f}개")
        print(f"최대 수집 필드: {field_counts.max()}개")
        print(f"최소 수집 필드: {field_counts.min()}개")

    return result_df

if __name__ == "__main__":
    test_results = test_optimized_scraper()
    print("\n테스트 완료! 결과는 scraped_optimized_test.csv에 저장되었습니다.")