import re
import logging
from app.core.constants import (
    SPONSOR_PATTERNS,
    SPECIAL_CASE_PATTERNS,
    SPONSOR_KEYWORDS,
    SPONSOR_CLASS_PATTERNS,
    NON_SPONSOR_CLASS_PATTERNS,
    STICKER_DOMAINS,
)
from bs4 import BeautifulSoup  # type: ignore

logger = logging.getLogger(__name__)

class PatternAnalyzerService:
    """텍스트 및 HTML 패턴 분석 관련 서비스 클래스"""
    
    # 중앙에서 관리되는 상수 사용
    SPONSOR_CLASS_PATTERNS = SPONSOR_CLASS_PATTERNS
    NON_SPONSOR_CLASS_PATTERNS = NON_SPONSOR_CLASS_PATTERNS
    STICKER_DOMAINS = STICKER_DOMAINS

    # 패턴 키만 추출하여 정규 표현식 패턴 목록 생성
    SPONSOR_TEXT_PATTERNS = list(SPONSOR_PATTERNS.keys())

    # 키워드 키만 추출
    SPONSOR_KEYWORDS = list(SPONSOR_KEYWORDS.keys())
    
    def check_ocr_text_for_sponsors(self, ocr_text: str, image_url: str = "") -> list:
        """OCR 텍스트에서 협찬 패턴을 검색합니다."""
        if not ocr_text:
            return []

        # 공백이 너무 많은 경우를 위해 정규화 처리 (문자 사이 공백 제거)
        normalized_text = re.sub(r"\s+", "", ocr_text)
        
        # 모든 발견된 패턴과 키워드 저장
        found_patterns = []

        # 스티커 도메인에서 온 짧은 OCR 텍스트 처리 (4글자 이내)
        if image_url and len(normalized_text) <= 4 and len(normalized_text) > 0:
            # 이미지 URL이 STICKER_DOMAINS 중 하나에 속하는지 확인
            if any(domain in image_url for domain in self.STICKER_DOMAINS):
                found_patterns.append({
                    "type": "sticker_text",
                    "pattern": "sticker_text",
                    "matched_text": ocr_text,
                    "probability": 0.8,  # 80% 확률
                    "version": "original"
                })
                logger.info(f"스티커 도메인({image_url})에서 짧은 텍스트 발견 (협찬 확률 80%): '{ocr_text}'")
                return found_patterns
                
        # 원본 텍스트와 정규화 텍스트 모두에서 검사
        for text_version in [ocr_text, normalized_text]:
            # 1. 단일 키워드 확인
            for keyword in self.SPONSOR_KEYWORDS:
                if keyword in text_version:
                    found_patterns.append(
                        {
                            "type": "keyword",
                            "pattern": keyword,
                            "matched_text": keyword,
                            "version": (
                                "normalized"
                                if text_version == normalized_text
                                else "original"
                            ),
                        }
                    )

            # 2. 복잡한 패턴 확인 (가능한 경우)
            if (
                text_version != normalized_text
            ):  # 정규화된 텍스트는 정규식 패턴에 맞지 않음
                for pattern in self.SPONSOR_TEXT_PATTERNS:
                    match = re.search(pattern, text_version)
                    if match:
                        matched_text = match.group(0)
                        found_patterns.append(
                            {
                                "type": "pattern",
                                "pattern": pattern,
                                "matched_text": matched_text,
                                "version": "original",
                            }
                        )

        # 3. 특수 케이스 검사 (모든 텍스트 버전)
        for special_case, _ in SPECIAL_CASE_PATTERNS.items():
            if "업체 + 지원/제공" == special_case:
                # "업체" + "지원/제공" 조합 확인 (순서 무관)
                if ("업체" in ocr_text or "업체" in normalized_text) and (
                    any(term in ocr_text for term in ["지원", "제공"])
                    or any(term in normalized_text for term in ["지원", "제공"])
                ):
                    found_patterns.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": ocr_text,
                        }
                    )
            elif "후기 + 지원/제공" == special_case:
                # "후기" + "지원/제공" 조합 확인
                if ("후기" in ocr_text or "후기" in normalized_text) and (
                    any(term in ocr_text for term in ["지원", "제공"])
                    or any(term in normalized_text for term in ["지원", "제공"])
                ):
                    found_patterns.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": ocr_text,
                        }
                    )
            elif "광고 + 콘텐츠" == special_case:
                # "광고" + "콘텐츠" 조합 확인
                if ("광고" in ocr_text or "광고" in normalized_text) and (
                    any(term in ocr_text for term in ["콘텐츠", "포스팅", "게시물"])
                    or any(
                        term in normalized_text
                        for term in ["콘텐츠", "포스팅", "게시물"]
                    )
                ):
                    found_patterns.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": ocr_text,
                        }
                    )
            elif "AD + 포스팅" == special_case:
                # "AD" + "포스팅" 조합 확인
                if (
                    "AD" in ocr_text
                    or "ad" in ocr_text.lower()
                    or "AD" in normalized_text
                ) and (
                    any(term in ocr_text for term in ["포스팅", "콘텐츠", "게시물"])
                    or any(
                        term in normalized_text
                        for term in ["포스팅", "콘텐츠", "게시물"]
                    )
                ):
                    found_patterns.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": ocr_text,
                        }
                    )

        return found_patterns
        
    def check_html_structure_for_sponsors(self, soup: BeautifulSoup) -> dict | None:
        """HTML 구조에서 협찬 관련 요소를 확인합니다."""
        sponsor_elements = []
        for pattern in self.SPONSOR_CLASS_PATTERNS:
            elements = soup.find_all(class_=re.compile(pattern))
            for elem in elements:
                # 협찬과 무관한 클래스를 가진 요소 제외
                elem_classes = " ".join(elem.get("class", []))
                if not any(
                    re.search(non_pattern, elem_classes)
                    for non_pattern in self.NON_SPONSOR_CLASS_PATTERNS
                ):
                    sponsor_elements.append(elem)
        
        if not sponsor_elements:
            return None
            
        # 각 요소의 클래스와 텍스트 정보 추가
        sponsor_element_details = []
        for elem in sponsor_elements:
            elem_class = elem.get("class", [])
            elem_text = elem.get_text(strip=True)[:100]  # 텍스트가 너무 길면 자름
            sponsor_element_details.append(
                {
                    "class": (
                        " ".join(elem_class)
                        if isinstance(elem_class, list)
                        else elem_class
                    ),
                    "text": elem_text if elem_text else "(텍스트 없음)",
                }
            )
        
        if sponsor_element_details:
            return {
                "is_sponsored": True,
                "element_type": "html_structure",
                "sponsor_elements": sponsor_element_details
            }
        
        return None 