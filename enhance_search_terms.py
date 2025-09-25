import pandas as pd
import re
from typing import List, Tuple

class SearchTermEnhancer:
    """검색어를 의미맥락 단위로 분리하여 검색 성공률 향상"""

    def __init__(self):
        # 의미 단위 키워드 사전
        self.compound_words = [
            '사회복지', '보건복지', '기초생활', '긴급복지', '사례관리',
            '역량평가', '문제해결', '동기부여', '리더십', '국가정책',
            '복지서비스', '복지정책', '저작권', '공문서', '기초연금',
            '임금보장', '생활보장', '북토크', '명강사', '공개강의'
        ]

        # 조사 및 연결어구
        self.particles = ['의', '을', '를', '이', '가', '와', '과', '에', '에서', '로', '으로']
        self.connectors = ['위한', '통해', '통한', '대한', '관한']

    def split_by_meaning_units(self, text: str) -> str:
        """의미맥락 단위로 텍스트 분리"""
        original = text

        # 1. 괄호 내용 처리
        # 괄호와 내용을 별도 토큰으로 분리
        text = re.sub(r'\(([^)]+)\)', r' \1 ', text)

        # 2. 특수문자 처리
        # 한자는 제거하고 영문은 유지
        text = re.sub(r'[\u4e00-\u9fff人]', '', text)
        text = re.sub(r'[!@#$%^&*_+=\-]', ' ', text)

        # 3. 복합명사 보호 (먼저 치환)
        protected_text = text
        replacements = {}
        for idx, compound in enumerate(self.compound_words):
            if compound in protected_text:
                placeholder = f"__COMPOUND{idx}__"
                replacements[placeholder] = compound
                protected_text = protected_text.replace(compound, placeholder)

        # 4. CamelCase 및 붙어있는 단어 분리
        # 대문자 앞에 공백 추가
        protected_text = re.sub(r'([가-힣])([A-Z])', r'\1 \2', protected_text)
        protected_text = re.sub(r'([a-z])([A-Z])', r'\1 \2', protected_text)

        # 5. 한글 단어 경계 감지 및 분리
        # 명사+명사 패턴 분리
        words = []
        temp_word = ""

        for char in protected_text:
            if char == ' ' or char in '.,':
                if temp_word:
                    words.append(temp_word)
                    temp_word = ""
                continue

            temp_word += char

            # 조사나 연결어구 발견 시 분리
            for particle in self.particles + self.connectors:
                if temp_word.endswith(particle) and len(temp_word) > len(particle):
                    # 조사/연결어 앞까지 단어로 추가
                    base = temp_word[:-len(particle)]
                    if base and not base.startswith('__COMPOUND'):
                        words.append(base)
                        words.append(particle)
                        temp_word = ""
                        break

        if temp_word:
            words.append(temp_word)

        # 6. 복합명사 복원
        restored_words = []
        for word in words:
            if word.startswith('__COMPOUND') and word.endswith('__'):
                restored_words.append(replacements.get(word, word))
            else:
                restored_words.append(word)

        # 7. 의미있는 단위로 재조합
        final_terms = []
        skip_next = False

        for i, word in enumerate(restored_words):
            if skip_next:
                skip_next = False
                continue

            # 조사/연결어와 다음 단어 연결
            if word in self.connectors and i < len(restored_words) - 1:
                final_terms.append(f"{word} {restored_words[i+1]}")
                skip_next = True
            elif word not in self.particles and len(word.strip()) > 1:
                final_terms.append(word)

        # 8. 중복 제거 및 정리
        final_terms = [term.strip() for term in final_terms if term.strip()]
        final_terms = list(dict.fromkeys(final_terms))  # 순서 유지하며 중복 제거

        # 너무 짧은 단어 제거 (1글자)
        final_terms = [term for term in final_terms if len(term) > 1]

        # 결과가 비어있으면 원본 반환
        if not final_terms:
            return original

        return ' '.join(final_terms)

    def analyze_improvement(self, original: str, enhanced: str) -> dict:
        """개선 효과 분석"""
        return {
            'original': original,
            'enhanced': enhanced,
            'original_length': len(original),
            'enhanced_terms': enhanced.split(),
            'term_count': len(enhanced.split()),
            'char_with_spaces': len(enhanced),
            'improvement_ratio': round(len(enhanced.split()) / max(1, len(original.split())), 2)
        }

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("검색어 개선 프로세스 시작")
    print("=" * 60)

    # 1. 원본 데이터 로드
    df = pd.read_csv('work.csv')
    print(f"\n[OK] 원본 교육과정 수: {len(df)}")

    enhancer = SearchTermEnhancer()

    # 2. 검색어 개선
    enhanced_terms = []
    improvement_stats = []

    for idx, row in df.iterrows():
        original = row['교육명']
        enhanced = enhancer.split_by_meaning_units(original)
        enhanced_terms.append(enhanced)

        stats = enhancer.analyze_improvement(original, enhanced)
        improvement_stats.append(stats)

        # 샘플 출력 (처음 10개)
        if idx < 10:
            print(f"\n[{idx+1}] AS-IS: {original}")
            print(f"    TO-BE: {enhanced}")
            print(f"    개선율: {stats['improvement_ratio']}x ({stats['term_count']} 검색어)")

    # 3. 개선된 데이터 저장
    df['검색어_원본'] = df['교육명']
    df['검색어_개선'] = enhanced_terms
    df['검색어_수'] = [len(term.split()) for term in enhanced_terms]
    df['개선율'] = [stat['improvement_ratio'] for stat in improvement_stats]

    df.to_csv('work_enhanced.csv', index=False, encoding='utf-8-sig')
    print("\n[OK] 개선된 검색어 파일 저장: work_enhanced.csv")

    # 4. 통계 분석
    print("\n" + "=" * 60)
    print("[ANALYSIS] AS-IS / TO-BE 분석 결과")
    print("=" * 60)

    avg_original_terms = df['교육명'].str.split().str.len().mean()
    avg_enhanced_terms = df['검색어_수'].mean()
    avg_improvement = df['개선율'].mean()

    print(f"""
    AS-IS (기존):
    - 평균 검색어 수: {avg_original_terms:.1f}개
    - 단일 문자열 검색
    - 정확 일치 필요

    TO-BE (개선):
    - 평균 검색어 수: {avg_enhanced_terms:.1f}개
    - 의미 단위 분리 검색
    - AND 조건 유연 매칭
    - 평균 개선율: {avg_improvement:.1f}x

    예상 효과:
    - 검색 매칭률 향상: {avg_improvement * 100 - 100:.0f}%
    - 누락 교육과정 감소
    - 더 정확한 결과 매칭
    """)

    # 5. 개선 효과가 큰 TOP 10
    df_sorted = df.sort_values('개선율', ascending=False)
    print("\n[TOP10] 개선 효과 TOP 10:")
    print("-" * 60)

    for idx, row in df_sorted.head(10).iterrows():
        print(f"{row['검색어_원본'][:30]:<30} → {row['개선율']:.1f}x 개선")

    print("\n[COMPLETE] 검색어 개선 완료!")
    print("다음 단계: 개선된 검색어로 스크래핑 실행")

    return df

if __name__ == "__main__":
    enhanced_df = main()