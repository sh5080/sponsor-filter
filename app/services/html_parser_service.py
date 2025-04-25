from bs4 import BeautifulSoup  # type: ignore
import re
import json
import logging
from app.core.constants import (
    STICKER_DOMAINS,
    STICKER_CLASSES,
)

logger = logging.getLogger(__name__)

class HTMLParserService:
    """HTML 파싱 및 요소 추출 관련 서비스 클래스"""
    
    # 중앙에서 관리되는 상수 사용
    STICKER_DOMAINS = STICKER_DOMAINS
    STICKER_CLASSES = STICKER_CLASSES
    
    def extract_first_sticker(self, soup: BeautifulSoup) -> dict | None:
        """첫 번째 스티커를 추출합니다."""
        # 1. 스티커 클래스로 찾기
        for sticker_class in self.STICKER_CLASSES:
            sticker_elements = soup.find_all(class_=re.compile(sticker_class))
            if sticker_elements:
                for elem in sticker_elements:
                    # 이미지 태그 찾기
                    img = elem.find("img")  # type: ignore
                    if img and img.get("src"):  # type: ignore
                        img_url = img.get("src")  # type: ignore
                        # 스티커 도메인 확인
                        if img_url and any(domain in img_url for domain in self.STICKER_DOMAINS):  # type: ignore
                            return {"url": img_url, "type": "class_based"}
                    
                    # 배경 이미지 스타일 확인
                    if elem.get("style") and "background-image" in elem.get("style", ""):  # type: ignore
                        style = elem.get("style")  # type: ignore
                        url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', str(style))
                        if url_match:
                            img_url = url_match.group(1)
                            # 스티커 도메인 확인
                            if any(
                                domain in img_url for domain in self.STICKER_DOMAINS
                            ):
                                return {"url": img_url, "type": "style_based"}
        
        # 2. data-linkdata 속성으로 찾기 (네이버 블로그 특유의 구조)
        elements_with_linkdata = soup.find_all(attrs={"data-linkdata": True})
        for elem in elements_with_linkdata:
            try:
                linkdata = json.loads(elem.get("data-linkdata"))
                if "src" in linkdata:
                    img_url = linkdata["src"]
                    # 스티커 도메인 확인
                    if any(domain in img_url for domain in self.STICKER_DOMAINS):
                        return {"url": img_url, "type": "linkdata_based"}
            except:
                pass
        
        # 3. 이미지 태그 중 스티커 도메인을 가진 것 찾기
        all_images = soup.find_all("img")
        for img in all_images:
            if img.get("src"):
                img_url = img.get("src")
                # 스티커 도메인 확인
                if any(domain in img_url for domain in self.STICKER_DOMAINS):
                    return {"url": img_url, "type": "img_based"}
        
        # 4. 배경 이미지 스타일을 가진 모든 요소 확인
        all_elements = soup.find_all(lambda tag: tag.get("style") and "background-image" in tag.get("style", ""))  # type: ignore
        for elem in all_elements:
            style = elem.get("style", "")
            url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if url_match:
                img_url = url_match.group(1)
                # 스티커 도메인 확인
                if any(domain in img_url for domain in self.STICKER_DOMAINS):
                    return {"url": img_url, "type": "background_based"}
        
        return None
    
    def extract_first_image(self, soup: BeautifulSoup) -> dict | None:
        """첫 번째 이미지를 본문 영역에서만 추출합니다. (스티커가 아닌 일반 이미지)"""
        # 네이버 블로그 본문 영역 찾기
        content_area = None

        # 1. 네이버 블로그 (모바일) 본문 영역 찾기
        possible_content_selectors = [
            ".se-main-container",  # 스마트에디터 2.0
            ".post_ct",  # 구버전 모바일
            "#viewTypeSelector",  # 구버전 PC
            ".se_component_wrap",  # 구버전 PC (스마트에디터 1.0)
            ".se-module-text",  # 텍스트 모듈
            ".sect_dsc",  # 모바일 본문
            ".se_card_container",  # 카드 컨테이너
            "#postViewArea",  # 일반 포스트
            ".post-content",  # 일반적인 블로그 본문 클래스
        ]

        for selector in possible_content_selectors:
            content_elements = soup.select(selector)
            if content_elements:
                content_area = content_elements[0]
                logger.info(f"본문 영역 발견: {selector}")
                break

        # 본문 영역을 찾지 못한 경우 전체 HTML에서 검색
        if not content_area:
            logger.info("본문 영역을 찾을 수 없어 전체 HTML에서 검색합니다.")
            content_area = soup
            
        # 스마트에디터 2.0 계층 구조에서 첫 번째 이미지 찾기 (se-component > se-image)
        # 1. se-image-resource 클래스를 가진 img 태그 직접 찾기 (가장 정확)
        se_image_resources = content_area.select(".se-image-resource")
        if se_image_resources:
            img = se_image_resources[0]  # 첫 번째 이미지만 처리
            if img.get("src"):
                img_url = img.get("src")
                logger.info(f"첫 번째 스마트에디터 이미지 리소스 발견: {img_url}")
                return {"url": img_url, "type": "se-image-resource"}
        
        # 2. se-component se-image 컴포넌트 찾기 - 가장 첫 번째 요소만 처리
        se_components = content_area.select(".se-component.se-image")
        if se_components:
            component = se_components[0]  # 첫 번째 컴포넌트만 처리
            
            # 이미지 모듈 찾기
            module = component.select_one(".se-module.se-module-image")
            if module:
                # 직접 이미지 리소스 찾기 (첫 번째 우선순위)
                img = module.select_one(".se-image-resource")
                if img and img.get("src"):
                    img_url = img.get("src")
                    logger.info(f"첫 번째 스마트에디터 이미지 발견 (직접 이미지): {img_url}")
                    return {"url": img_url, "type": "se-component-image-resource"}
                
                # 이미지 리소스가 없으면 링크데이터 확인
                link = module.select_one(".se-module-image-link")
                if link and link.get("data-linkdata"):
                    try:
                        link_data_str = str(link.get("data-linkdata"))
                        link_data_str = link_data_str.replace("&quot;", '"')
                        link_data = json.loads(link_data_str)
                        
                        if "src" in link_data:
                            img_url = link_data["src"]
                            logger.info(f"첫 번째 스마트에디터 이미지 발견 (링크데이터): {img_url}")
                            return {"url": img_url, "type": "se-component-image"}
                    except Exception as e:
                        logger.warning(f"data-linkdata 파싱 오류: {str(e)}")
                
        # 일반 이미지 태그 검색 - 첫 번째만 처리
        all_images = content_area.find_all("img")
        for img in all_images:
            img_url = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            
            # 스티커 도메인 제외
            if img_url and not any(domain in img_url for domain in self.STICKER_DOMAINS):
                if img_url.startswith(("http://", "https://")):
                    logger.info(f"일반 이미지 발견: {img_url}")
                    return {"url": img_url, "type": "img_tag"}
        
        # 이미지를 찾지 못한 경우
        logger.info("본문에서 유효한 이미지를 찾을 수 없습니다.")
        return None
    
    def find_first_paragraph(self, soup: BeautifulSoup) -> tuple[str, str] | None:
        """첫 번째 문단과 초반부의 인용구를 찾습니다."""
        # 본문 영역 찾기
        content_area = None
        possible_content_selectors = [
            ".se-main-container",  # 스마트에디터 2.0
            ".post_ct",            # 구버전 모바일
            "#viewTypeSelector",   # 구버전 PC
            ".se_component_wrap",  # 구버전 PC (스마트에디터 1.0)
            ".se-module-text",     # 텍스트 모듈
            ".sect_dsc",           # 모바일 본문
            ".se_card_container",  # 카드 컨테이너
            "#postViewArea",       # 일반 포스트
            ".post-content",       # 일반적인 블로그 본문 클래스
        ]
        
        for selector in possible_content_selectors:
            content_elements = soup.select(selector)
            if content_elements:
                content_area = content_elements[0]
                logger.info(f"본문 영역 발견: {selector}")
                break
        
        if not content_area:
            logger.info("본문 영역을 찾을 수 없어 전체 HTML에서 검색합니다.")
            content_area = soup

        # 첫 번째 문단과 인용구를 저장할 변수
        first_paragraph = ""
        quotation_text = ""
        selector_used = ""

        # 1. 인용구 확인 (처음 2개까지만)
        quotation_selectors = [
            ".se-quotation-container",  # 스마트에디터 2.0 인용구
            "blockquote"               # 일반 인용구
        ]
        
        for selector in quotation_selectors:
            quotes = content_area.select(selector)[:2]  # 처음 2개만
            for quote in quotes:
                text = quote.get_text(strip=True)
                if text and len(text) > 5:
                    quotation_text = text
                    logger.info(f"인용구 발견: {text[:100]}...")
                    break
            if quotation_text:
                break

        # 2. 일반 문단 확인
        paragraph_selectors = [
            ".se-text-paragraph",  # 스마트에디터 2.0 문단
            ".se-module-text p",   # 스마트에디터 모듈 내 문단
            ".post_ct p",          # 일반 모바일 블로그 문단
            ".sect_dsc p",         # 모바일 본문 문단
            "p"                    # 일반 문단 태그
        ]
        
        for selector in paragraph_selectors:
            paragraphs = content_area.select(selector)
            if paragraphs:
                text = paragraphs[0].get_text(strip=True)
                if text and len(text) > 5:
                    first_paragraph = text
                    selector_used = selector
                    logger.info(f"첫 번째 문단 발견: {text[:100]}...")
                    break

        # 문단과 인용구 중 하나라도 발견된 경우
        if first_paragraph or quotation_text:
            # 둘 다 있는 경우 합치고, 하나만 있는 경우 있는 것만 반환
            combined_text = " ".join(filter(None, [first_paragraph, quotation_text]))
            return combined_text, selector_used
        
        return None 