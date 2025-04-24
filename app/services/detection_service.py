from bs4 import BeautifulSoup  # type: ignore
import re
from app.models.schemas import SponsorDetectionResult
import logging
import os
from app.core.constants import (
    SPONSOR_PATTERNS,
    SPONSOR_KEYWORDS,
    NON_SPONSOR_CLASS_PATTERNS,
    STICKER_DOMAINS,
    STICKER_CLASSES,
    SPONSOR_CLASS_PATTERNS,
)
from pathlib import Path
from .ocr_service import OCRService
from .html_crawler_service import HTMLCrawlerService
from .html_parser_service import HTMLParserService
from .pattern_analyzer_service import PatternAnalyzerService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
TESSDATA_PATH = os.path.join(PROJECT_ROOT, "tessdata")

# Tesseract 환경 변수 설정 (아직 설정되지 않은 경우에만)
if not os.environ.get("TESSDATA_PREFIX") and os.path.exists(TESSDATA_PATH):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH
    logger.info(f"TESSDATA_PREFIX 환경 변수를 {TESSDATA_PATH}로 설정했습니다.")


class DetectionService:
    """협찬 콘텐츠를 감지하는 서비스"""
    
    def __init__(self):
        """서비스 초기화 및 하위 서비스 인스턴스 생성"""
        self.ocr_service = OCRService()
        self.html_crawler = HTMLCrawlerService()
        self.html_parser = HTMLParserService()
        self.pattern_analyzer = PatternAnalyzerService()
    
    # 중앙에서 관리되는 상수 사용
    STICKER_DOMAINS = STICKER_DOMAINS
    STICKER_CLASSES = STICKER_CLASSES
    SPONSOR_CLASS_PATTERNS = SPONSOR_CLASS_PATTERNS
    NON_SPONSOR_CLASS_PATTERNS = NON_SPONSOR_CLASS_PATTERNS

    # 패턴 키만 추출하여 정규 표현식 패턴 목록 생성
    SPONSOR_TEXT_PATTERNS = list(SPONSOR_PATTERNS.keys())

    # 키워드 키만 추출
    SPONSOR_KEYWORDS = list(SPONSOR_KEYWORDS.keys())

    # 스티커에서 협찬 패턴 확인 함수
    async def check_sticker_for_sponsors(self, soup: BeautifulSoup) -> dict | None:
        """첫 번째 스티커에서 협찬 패턴을 확인합니다."""
        first_sticker = self.html_parser.extract_first_sticker(soup)
        if not first_sticker:
            return None
            
        img_url = self.ocr_service.normalize_image_url(first_sticker["url"])
        logger.info(f"스티커 OCR 처리 중: {img_url} (타입: {first_sticker['type']})")
        
        # OCR 처리
        ocr_text = await self.ocr_service.process_image_ocr(img_url)
        logger.info(f"스티커 OCR 결과: {ocr_text}")
        
        # OCR 결과에서 협찬 패턴 확인 (이미지 URL 전달)
        found_patterns = self.pattern_analyzer.check_ocr_text_for_sponsors(ocr_text, img_url)
        
        if found_patterns:
            return {
                "is_sponsored": True,
                "element_type": "sticker",
                "img_url": img_url,
                "ocr_text": ocr_text,
                "found_patterns": found_patterns
            }
        
        return {
            "is_sponsored": False,
            "element_type": "sticker",
            "img_url": img_url,
            "ocr_text": ocr_text
        }
    
    # 이미지에서 협찬 패턴 확인 함수
    async def check_image_for_sponsors(self, soup: BeautifulSoup) -> dict | None:
        """첫 번째 이미지에서 협찬 패턴을 확인합니다."""
        first_image = self.html_parser.extract_first_image(soup)
        if not first_image:
            return None
            
        img_url = self.ocr_service.normalize_image_url(first_image["url"])
        logger.info(f"이미지 OCR 처리 중: {img_url} (타입: {first_image['type']})")
        
        # OCR 처리
        ocr_text = await self.ocr_service.process_image_ocr(img_url)
        logger.info(f"이미지 OCR 결과: {ocr_text}")
        
        # OCR 결과에서 협찬 패턴 확인 (이미지 URL 전달)
        found_patterns = self.pattern_analyzer.check_ocr_text_for_sponsors(ocr_text, img_url)
        
        if found_patterns:
            return {
                "is_sponsored": True,
                "element_type": "image",
                "img_url": img_url,
                "ocr_text": ocr_text,
                "found_patterns": found_patterns
            }
        
        return {
            "is_sponsored": False,
            "element_type": "image",
            "img_url": img_url,
            "ocr_text": ocr_text
        }
    
    # 본문에서 협찬 패턴 확인 함수
    def check_paragraph_for_sponsors(self, soup: BeautifulSoup) -> dict | None:
        """첫 번째 문단에서 협찬 패턴을 확인합니다."""
        # 본문에서 첫 번째 문단 추출
        paragraph_result = self.html_parser.find_first_paragraph(soup)
        if not paragraph_result:
            logger.info("첫 번째 문단을 찾을 수 없습니다.")
            return None
            
        paragraph_text, selector_used = paragraph_result
        
        # 문단에서 협찬 패턴 확인
        found_patterns = self.pattern_analyzer.check_ocr_text_for_sponsors(paragraph_text)
        
        if found_patterns:
            return {
                "is_sponsored": True,
                "element_type": "paragraph",
                "text": paragraph_text,
                "found_patterns": found_patterns
            }
        
        return {
            "is_sponsored": False,
            "element_type": "paragraph",
            "text": paragraph_text
        }
    

    async def detect_sponsored_content(
        self, html_content: str, blog_url: str | None = None
    ) -> SponsorDetectionResult:
        """HTML 콘텐츠에서 협찬 콘텐츠를 감지합니다."""
        indicators = []
        debug_info = {}
        structured_indicators = []  # 구조화된 지표 초기화
        
        if blog_url:
            logger.info(f"직접 크롤링을 진행합니다: {blog_url}")
            fetched_content = await self.html_crawler.get_full_blog_content(blog_url)
            
            if fetched_content:
                html_content = fetched_content
                logger.info(f"크롤링으로 HTML 콘텐츠를 가져왔습니다: {len(html_content)} 바이트")
            else:
                logger.error("블로그 콘텐츠를 가져오지 못했습니다.")
                return SponsorDetectionResult(
                    is_sponsored=False,
                    indicators=[],  # 빈 리스트로 설정
                    debug_info={"error": "블로그 콘텐츠를 가져오지 못했습니다."}
                )
        
        # HTML 파싱
        soup = BeautifulSoup(html_content, "html.parser")
        sponsored_result = None
        
        # 1. 스티커 확인
        logger.info("1단계: 첫 번째 스티커 확인")
        sticker_result = await self.check_sticker_for_sponsors(soup)
        debug_info["sticker_check"] = sticker_result
        
        if sticker_result and sticker_result["is_sponsored"]:
            logger.info("스티커에서 협찬 패턴 발견")
            sponsored_result = sticker_result
        else:
            # 2. 이미지 확인
            logger.info("2단계: 첫 번째 이미지 확인")
            image_result = await self.check_image_for_sponsors(soup)
            debug_info["image_check"] = image_result
            
            if image_result and image_result["is_sponsored"]:
                logger.info("이미지에서 협찬 패턴 발견")
                sponsored_result = image_result
            else:
                # 3. 본문 확인
                logger.info("3단계: 첫 번째 문단 확인")
                paragraph_result = self.check_paragraph_for_sponsors(soup)
                debug_info["paragraph_check"] = paragraph_result
                
                if paragraph_result and paragraph_result["is_sponsored"]:
                    logger.info("문단에서 협찬 패턴 발견")
                    sponsored_result = paragraph_result
                else:
                    # 4. HTML 구조 확인
                    logger.info("4단계: HTML 구조 확인")
                    html_structure_result = self.pattern_analyzer.check_html_structure_for_sponsors(soup)
                    debug_info["html_structure_check"] = html_structure_result
                    
                    if html_structure_result and html_structure_result["is_sponsored"]:
                        logger.info("HTML 구조에서 협찬 패턴 발견")
                        sponsored_result = html_structure_result
        
        # 협찬 여부 최종 판단
        is_sponsored = sponsored_result is not None and sponsored_result["is_sponsored"]
        
        # 협찬 지표 구성
        if is_sponsored and sponsored_result:
            element_type = sponsored_result["element_type"]
            
            if element_type in ["sticker", "image"]:
                # 스티커 또는 이미지 OCR 결과에서 발견된 패턴 처리
                for pattern_info in sponsored_result["found_patterns"]:
                    pattern_type = pattern_info["type"]
                    pattern = pattern_info["pattern"]
                    matched_text = pattern_info["matched_text"]
                    version = pattern_info.get("version", "")
                    
                    # 텍스트 형태 지표 추가
                    version_text = f", 버전: {version}" if version else ""
                    indicator_text = f"{element_type.capitalize()} OCR에서 협찬 {pattern_type} 발견: '{matched_text}' (패턴: {pattern}, 이미지: {sponsored_result['img_url']}{version_text})"
                    indicators.append(indicator_text)
                    
                    # 구조화된 지표 추가
                    structured_indicator = {
                        "type": pattern_type,
                        "pattern": pattern,
                        "matched_text": matched_text,
                        "source": f"{element_type}_ocr",
                        "source_info": {
                            "image_url": sponsored_result["img_url"],
                            "detection_method": version if version else "original"
                        }
                    }
                    structured_indicators.append(structured_indicator)
                    
                    logger.info(indicator_text)
                    
            elif element_type == "paragraph":
                # 문단에서 발견된 패턴 처리
                for pattern_info in sponsored_result["found_patterns"]:
                    pattern_type = pattern_info["type"]
                    pattern = pattern_info["pattern"]
                    matched_text = pattern_info["matched_text"]
                    
                    # 텍스트 형태 지표 추가
                    indicator_text = f"첫 번째 문단에서 협찬 {pattern_type} 발견: '{matched_text}' (패턴: {pattern})"
                    indicators.append(indicator_text)
                    
                    # 구조화된 지표 추가
                    paragraph_text = sponsored_result["text"]
                    structured_indicator = {
                        "type": pattern_type,
                        "pattern": pattern,
                        "matched_text": matched_text,
                        "source": "first_paragraph",
                        "source_info": {
                            "text": paragraph_text[:100] + "..." if len(paragraph_text) > 100 else paragraph_text
                        }
                    }
                    structured_indicators.append(structured_indicator)
                    
                    logger.info(indicator_text)
                    
            elif element_type == "html_structure":
                # HTML 구조에서 발견된 패턴 처리
                indicators.append(
                    f"협찬 관련 HTML 요소 발견: {len(sponsored_result['sponsor_elements'])}개"
                )
                
                for i, detail in enumerate(sponsored_result["sponsor_elements"], 1):
                    indicators.append(
                        f"  {i}. 클래스: {detail['class']}, 텍스트: {detail['text']}"
                    )
                    
                    # 구조화된 지표 추가
                    structured_indicator = {
                        "type": "html_element",
                        "pattern": detail["class"],
                        "matched_text": detail["text"],
                        "source": "html_element",
                        "source_info": {
                            "class": detail["class"]
                        }
                    }
                    structured_indicators.append(structured_indicator)
                    
                logger.info(
                    f"협찬 관련 HTML 요소 발견: {len(sponsored_result['sponsor_elements'])}개"
                )
        
        # 디버깅 정보 추가
        debug_info["is_sponsored"] = is_sponsored
        debug_info["indicators"] = indicators
        debug_info["structured_indicators"] = structured_indicators
        
        logger.info(f"협찬 감지 결과: {is_sponsored}, 지표 수: {len(indicators)}")
        
        return SponsorDetectionResult(
            is_sponsored=is_sponsored,
            indicators=structured_indicators, 
            debug_info=debug_info,
        )

