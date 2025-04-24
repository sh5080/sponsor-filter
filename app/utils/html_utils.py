"""
HTML 처리 및 크롤링 관련 유틸리티 함수를 제공하는 모듈입니다.
이미지 다운로드, HTML 파싱, 스티커 및 이미지 추출 등의 기능을 포함합니다.
"""

import aiohttp  # type: ignore
import logging
import re
from typing import Dict, Any
from bs4 import BeautifulSoup, Tag
from urllib.parse import urlparse, urljoin
from app.core.constants import STICKER_DOMAINS, STICKER_CLASSES

# 로깅 설정
logger = logging.getLogger(__name__)

# 세션 객체 (전역변수 - 애플리케이션 생명주기 동안 재사용)
session = None

async def get_session() -> aiohttp.ClientSession:
    """비동기 HTTP 세션을 가져오거나 생성합니다."""
    global session
    if session is None or session.closed:
        timeout = aiohttp.ClientTimeout(total=10)  # 10초 타임아웃
        session = aiohttp.ClientSession(timeout=timeout)
    return session

async def download_image(image_url: str) -> bytes | None:
    """이미지 URL에서 이미지 데이터를 다운로드합니다."""
    if not image_url:
        return None
    
    try:
        session = await get_session()
        async with session.get(image_url) as response:
            if response.status == 200:
                return await response.read()
            else:
                logger.warning(f"이미지 다운로드 실패: {image_url} (상태 코드: {response.status})")
                return None
    except Exception as e:
        logger.error(f"이미지 다운로드 중 오류 발생: {str(e)} - URL: {image_url}")
        return None

async def get_full_blog_content(blog_url: str) -> str | None:
    """블로그 URL에서 전체 HTML 컨텐츠를 가져옵니다."""
    if not blog_url:
        return None
    
    try:
        session = await get_session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with session.get(blog_url, headers=headers) as response:
            if response.status == 200:
                return await response.text()
            else:
                logger.warning(f"블로그 내용 가져오기 실패: {blog_url} (상태 코드: {response.status})")
                return None
    except Exception as e:
        logger.error(f"블로그 내용 가져오기 중 오류 발생: {str(e)} - URL: {blog_url}")
        return None

def has_background_image(tag: Tag) -> bool:
    """태그가 배경 이미지 스타일을 가지고 있는지 확인합니다."""
    style = tag.get('style', '')
    if style and isinstance(style, str) and 'background-image' in style:
        return True
    return False

def extract_first_sticker(html_content: str) -> Dict[str, Any] | None:
    """HTML 컨텐츠에서 첫 번째 스티커를 추출합니다."""
    if not html_content:
        return None
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 스티커를 포함할 수 있는 모든 img 태그 검색
        sticker_imgs = []
        
        # 1. 직접 img 태그로 스티커 찾기
        for img in soup.find_all("img"):
            img_src = img.get("src", "")
            if not img_src:
                continue
            
            # Reviewnote.co.kr 스티커 케이스
            if img.get("data-linkdata") and any(
                domain in img_src for domain in STICKER_DOMAINS
            ):
                sticker_imgs.append({
                    "url": img_src,
                    "alt": img.get("alt", ""),
                    "class": img.get("class", []),
                    "source": "data-linkdata"
                })
                continue
                
            # 스티커 도메인 확인
            if any(domain in img_src for domain in STICKER_DOMAINS):
                # 스티커 클래스 확인 (클래스가 있는 경우)
                if img.get("class"):
                    class_str = " ".join(img.get("class", []))
                    if any(sticker_class in class_str for sticker_class in STICKER_CLASSES):
                        sticker_imgs.append({
                            "url": img_src,
                            "alt": img.get("alt", ""),
                            "class": img.get("class", []),
                            "source": "class_match"
                        })
                        continue
                
                # 클래스 없이 스티커 도메인만으로 추가
                sticker_imgs.append({
                    "url": img_src,
                    "alt": img.get("alt", ""),
                    "class": img.get("class", []),
                    "source": "domain_only"
                })
        
        # 2. 배경 이미지로 설정된 스티커 찾기
        for tag in soup.find_all(has_background_image):
            style = tag.get('style', '')
            # 배경 이미지 URL 추출
            match = re.search(r'background-image\s*:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            if match:
                img_src = match.group(1)
                
                # 상대 URL을 절대 URL로 변환
                if img_src.startswith('/'):
                    parsed_url = urlparse(html_content)
                    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                    img_src = urljoin(base_url, img_src)
                
                # 스티커 도메인 확인
                if any(domain in img_src for domain in STICKER_DOMAINS):
                    sticker_imgs.append({
                        "url": img_src,
                        "alt": "",  # 배경 이미지에는 alt 속성 없음
                        "class": tag.get("class", []),
                        "source": "background_image"
                    })
        
        # 스티커가 있으면 첫 번째 스티커 반환
        if sticker_imgs:
            return sticker_imgs[0]
        
        return None
    except Exception as e:
        logger.error(f"HTML에서 스티커 추출 중 오류 발생: {str(e)}")
        return None

def extract_first_image(html_content: str) -> str | None:
    """HTML 컨텐츠에서 첫 번째 이미지 URL을 추출합니다."""
    if not html_content:
        return None
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 이미지 우선순위 지정
        # 1. 메인 컨테이터 찾기 시도
        main_content = soup.find(
            "div", class_=["se-main-container", "post-content", "article"]
        )
        
        # 컨테이너에서 검색할 태그 지정
        container = main_content if main_content else soup
        
        # container가 None인지 확인
        if not container:
            return None
            
        # container가 Tag 타입인지 확인
        if not isinstance(container, Tag):
            container = soup
        
        # 2. 이미지 찾기
        for img in container.find_all("img"):
            img_src = img.get("src")
            if img_src:
                # 특정 작은 아이콘, 프로필 이미지 등 무시
                if any(
                    x in img_src.lower()
                    for x in [
                        "icon", 
                        "profile", 
                        "avatar", 
                        "logo",
                        "blank.gif",
                        "emot"
                    ]
                ):
                    continue
                
                # 이미지 크기가 지정된 경우 작은 크기 이미지 건너뛰기
                width_str = img.get("width", "")
                if width_str and width_str.isdigit() and int(width_str) < 100:
                    continue
                
                height_str = img.get("height", "")
                if height_str and height_str.isdigit() and int(height_str) < 100:
                    continue
                
                # 유효한 이미지 발견시 반환
                return img_src
        
        # 3. 배경 이미지 스타일 찾기
        for tag in container.find_all(has_background_image):
            style = tag.get('style', '')
            match = re.search(r'background-image\s*:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            if match:
                img_src = match.group(1)
                
                # 작은 아이콘 건너뛰기
                if any(
                    x in img_src.lower()
                    for x in [
                        "icon", 
                        "profile", 
                        "avatar", 
                        "logo", 
                        "emot"
                    ]
                ):
                    continue
                
                # 유효한 배경 이미지 발견시 반환
                return img_src
        
        return None
    except Exception as e:
        logger.error(f"HTML에서 이미지 추출 중 오류 발생: {str(e)}")
        return None

async def close_session():
    """HTTP 세션을 닫습니다. 애플리케이션 종료 시 호출해야 합니다."""
    global session
    if session and not session.closed:
        await session.close()
        session = None 