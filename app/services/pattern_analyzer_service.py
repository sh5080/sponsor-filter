import unicodedata
import re
import logging
from app.core.constants import (
    EXACT_SPONSOR_KEYWORDS_PATTERNS,
    SPECIAL_CASE_PATTERNS,
    SPONSOR_KEYWORDS,
    SPONSOR_CLASS_PATTERNS,
)

logger = logging.getLogger(__name__)

class PatternAnalyzerService:
    """텍스트 및 HTML 패턴 분석 관련 서비스 클래스"""
    
    # 키워드 키만 추출
    SPONSOR_KEYWORDS = list(SPONSOR_KEYWORDS.keys())
    
    def check_text_for_sponsors(self, text: str, source: str = "description") -> list:
        """텍스트에서 협찬 패턴을 검색합니다. (FilterService와 공유하는 메서드)"""
        if not text:
            return []

        # 유니코드 정규화
        normalized = unicodedata.normalize('NFKC', text)
        # 공백이 너무 많은 경우를 위해 정규화 처리 (문자 사이 공백 제거)
        normalized_text = re.sub(r"\s+", "", normalized)
        
        # 모든 발견된 패턴과 키워드 저장
        found_patterns = []
        logger.info(f"정규화된 텍스트: {normalized_text}")
        # 1. 정확한 협찬 키워드 패턴 확인 (즉시 90% 확률로 반환)
        
        for keyword in EXACT_SPONSOR_KEYWORDS_PATTERNS:
            if re.search(re.escape(keyword), normalized_text):
                found_patterns.append({
                    "type": "exact_keyword_regex",
                    "pattern": keyword,
                    "matched_text": normalized_text,
                    "probability": 0.9,
                    "source": source
                })
                logger.info(f"정확한 협찬 키워드 발견 (정규식 탐색): '{keyword}'")
                return found_patterns
        
        # 2. 일반 키워드 확인
        for keyword, probability in SPONSOR_KEYWORDS.items():
            if keyword in normalized_text:
                found_patterns.append({
                    "type": "keyword",
                    "pattern": keyword,
                    "matched_text": keyword,
                    "probability": probability,
                    "source": source
                })
                logger.info(f"협찬 키워드 발견 (협찬 확률 {probability*100}%): '{keyword}'")
        
        # 3. 특수 케이스 검사
        for case_name, case_info in SPECIAL_CASE_PATTERNS.items():
            terms1 = case_info["terms1"]
            terms2 = case_info["terms2"]
            probability = case_info.get("probability", 0.85)
            
            # 정규화된 텍스트에서 검사
            if any(term in normalized_text for term in terms1) and \
               any(term in normalized_text for term in terms2):
                found_patterns.append({
                    "type": "special_case",
                    "pattern": case_name,
                    "matched_text": normalized_text,
                    "probability": probability,
                    "source": source
                })
                logger.info(f"특수 케이스 발견 (협찬 확률 {probability*100}%): '{case_name}' (텍스트: {normalized_text})")
        
        return found_patterns
    
    def check_ocr_text_for_sponsors(self, ocr_text: str) -> list:
        """OCR 텍스트에서 협찬 패턴을 검색합니다."""
        # 기본 텍스트 검사 로직 재사용
        return self.check_text_for_sponsors(ocr_text, source="ocr")
    
    def analyze_html_elements(self, elements):
        """HTML 요소에서 협찬 패턴을 분석합니다."""
        found_patterns = []
        
        if not elements:
            return found_patterns
        
        for elem_detail in elements:
            # 클래스와 텍스트 정규화
            elem_class = re.sub(r"\s+", "", elem_detail.get('class', '')).lower()
            elem_text = elem_detail.get('text', '')
            
            # 1. 클래스에서 정확한 협찬 키워드 확인 (즉시 반환)
            for exact_keyword in EXACT_SPONSOR_KEYWORDS_PATTERNS:
                if exact_keyword in elem_class:
                    found_patterns.append({
                        "type": "exact_keyword",
                        "pattern": exact_keyword,
                        "matched_text": elem_detail.get('class', ''),
                        "probability": 0.9,  # 90% 확률
                        "source": "html_class"
                    })
                    logger.info(f"HTML 클래스에서 정확한 협찬 키워드 발견 (협찬 확률 90%): '{exact_keyword}'")
                    return found_patterns  # 즉시 반환
            
            # 2. 클래스에 협찬 관련 키워드가 있는지 확인
            for keyword in SPONSOR_CLASS_PATTERNS:
                if keyword in elem_class:
                    found_patterns.append({
                        "type": "html_class",
                        "pattern": keyword,
                        "matched_text": elem_detail.get('class', ''),
                        "probability": 0.9,  # 90% 확률
                        "source": "html_class"
                    })
                    logger.info(f"HTML 클래스에서 협찬 키워드 발견 (협찬 확률 90%): '{keyword}' (클래스: {elem_detail.get('class', '')})")
            
            # 3. 텍스트에서 협찬 패턴 확인
            text_patterns = self.check_text_for_sponsors(elem_text, source="html_text")
            found_patterns.extend(text_patterns)
        
        return found_patterns
    
    def analyze_detection_result(self, detection_result):
        """감지 결과를 분석하여 협찬 확률을 계산합니다."""
        found_patterns = []
        
        # 1. 스티커 OCR 결과 분석
        sticker_ocr = detection_result.get('debug_info', {}).get('sticker_ocr', '')
    
        if sticker_ocr:
            ocr_patterns = self.check_ocr_text_for_sponsors(sticker_ocr)
            found_patterns.extend(ocr_patterns)
        
        # 2. HTML 요소 분석
        sponsor_elements = []
        indicators = detection_result.get('indicators', [])
        
        # 한 번의 반복으로 모든 HTML 요소 추출
        for i, indicator in enumerate(indicators):
            if indicator.startswith("협찬 관련 HTML 요소 발견:"):
                # 하위 항목 추출
                j = i + 1
                while j < len(indicators) and indicators[j].startswith("  "):
                    parts = indicators[j].split(": ", 1)
                    if len(parts) > 1:
                        class_text = parts[1].split(", 텍스트: ")
                        if len(class_text) > 1:
                            sponsor_elements.append({
                                'class': class_text[0].replace("클래스: ", ""),
                                'text': class_text[1]
                            })
                    j += 1
        
        if sponsor_elements:
            html_patterns = self.analyze_html_elements(sponsor_elements)
            found_patterns.extend(html_patterns)
        
        # 3. 최종 확률 계산
        max_probability = 0
        if found_patterns:
            max_probability = max(pattern.get('probability', 0) for pattern in found_patterns)
        
        return {
            "is_sponsored": max_probability >= 0.7,  # 70% 이상이면 협찬으로 판단
            "probability": max_probability,
            "patterns": found_patterns
        } 