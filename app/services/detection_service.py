from bs4 import BeautifulSoup
import re
from app.models.schemas import SponsorDetectionResult
import logging
import aiohttp
import pytesseract
import tempfile
import os
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

class DetectionService:
    """협찬 콘텐츠를 감지하는 서비스"""
    
    # 스티커 도메인 패턴
    STICKER_DOMAINS = [
        "storep-phinf.pstatic.net", 
        "post-phinf.pstatic.net",
        "ssl.pstatic.net",
        "cometoplay.kr"
    ]
    
    # 스티커 클래스 패턴
    STICKER_CLASSES = [
        "se-sticker", "sticker", "_img", "sponsor-tag", "ad-tag"
    ]
    
    # 협찬 관련 클래스 패턴 (정확한 패턴만 포함)
    SPONSOR_CLASS_PATTERNS = [
        r'sponsor', r'ad-tag', r'promotion', r'체험단', r'협찬', r'revu'
    ]
    
    # 협찬과 무관한 클래스 패턴 (제외할 패턴)
    NON_SPONSOR_CLASS_PATTERNS = [
        r'buddy', r'loading', r'head', r'map', r'lazy'
    ]
    
    # 협찬 문구 패턴 (정확한 패턴)
    SPONSOR_TEXT_PATTERNS = [
        r'(제공|지원)받아',
        r'(원고료|소정의).{0,10}(제공|지원)',
        r'(체험|방문).{0,10}후기',
        r'(업체|제품).{0,10}(제공|지원)',
        r'(무상|무료).{0,10}(제공|지원)',
        r'(협찬|스폰서).{0,10}(포스팅|후기)',
        r'업체.{0,15}(제공|지원)받아',
        r'업체.{0,15}후기',
        r'제품.{0,15}후기',
        r'(제공|지원).{0,5}받아.{0,10}후기'
    ]
    
    # 협찬 키워드 (단일 키워드)
    SPONSOR_KEYWORDS = [
        '협찬', '제공', '지원', '체험단', '원고료', '무상', '무료', '스폰서', '제품제공'
    ]
    
    @staticmethod
    async def get_full_blog_content(blog_url: str) -> str:
        """블로그 URL에서 전체 HTML 콘텐츠를 가져옵니다."""
        try:
            # 모바일 버전 URL로 변환 (더 단순한 구조)
            if "blog.naver.com" in blog_url and "m.blog.naver.com" not in blog_url:
                blog_url = blog_url.replace("blog.naver.com", "m.blog.naver.com")
            
            # 다양한 User-Agent 설정 (차단 방지)
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://m.search.naver.com/',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-site',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(blog_url, timeout=10) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        
                        # 차단 여부 확인
                        if "비정상적인 접근" in html_content or "로봇" in html_content or "자동화된 접근" in html_content:
                            logger.error(f"네이버에서 차단되었습니다: {blog_url}")
                            print(f"네이버에서 차단되었습니다: {blog_url}")
                            return None
                        
                        logger.info(f"블로그 콘텐츠 가져오기 성공: {blog_url}")
                        return html_content
                    else:
                        logger.warning(f"블로그 콘텐츠 가져오기 실패: {blog_url}, 상태 코드: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"블로그 콘텐츠 가져오기 중 오류 발생: {blog_url}, 오류: {str(e)}")
            return None
    
    @staticmethod
    async def download_image(image_url: str) -> bytes:
        """이미지 URL에서 이미지를 다운로드합니다."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Referer': 'https://m.blog.naver.com/',
                'Accept': 'image/avif,image/webp,*/*',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Connection': 'keep-alive'
            }
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(image_url, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"이미지 다운로드 성공: {image_url}")
                        return await response.read()
                    else:
                        logger.warning(f"이미지 다운로드 실패: {image_url}, 상태 코드: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"이미지 다운로드 중 오류 발생: {image_url}, 오류: {str(e)}")
            return None
    
    @staticmethod
    async def extract_text_from_image(image_data: bytes) -> str:
        """이미지에서 텍스트를 추출합니다. 한국어 OCR에 최적화되었습니다."""
        if not image_data:
            return ""
        
        try:
            # 임시 파일에 이미지 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # 한국어 OCR 수행 (PSM 모드 6: 단일 텍스트 블록으로 처리)
                text = pytesseract.image_to_string(temp_file_path, lang='kor', config='--psm 6 --oem 3')
            except Exception as e:
                logger.warning(f"한국어 OCR 실패, 기본 OCR로 대체: {str(e)}")
                # 기본 OCR로 대체
                text = pytesseract.image_to_string(temp_file_path, config='--psm 6 --oem 3')
            
            # 임시 파일 삭제
            os.unlink(temp_file_path)
            
            # 텍스트 정리 (줄바꿈, 여러 공백 등 처리)
            text = re.sub(r'\s+', ' ', text).strip()
            
            return text
        except Exception as e:
            logger.error(f"이미지에서 텍스트 추출 중 오류 발생: {str(e)}")
            return ""
    
    def extract_first_sticker(self, soup: BeautifulSoup) -> dict:
        """첫 번째 스티커를 추출합니다."""
        # 1. 스티커 클래스로 찾기
        for sticker_class in self.STICKER_CLASSES:
            sticker_elements = soup.find_all(class_=re.compile(sticker_class))
            if sticker_elements:
                for elem in sticker_elements:
                    # 이미지 태그 찾기
                    img = elem.find('img')
                    if img and img.get('src'):
                        img_url = img.get('src')
                        # 스티커 도메인 확인
                        if any(domain in img_url for domain in self.STICKER_DOMAINS):
                            return {'url': img_url, 'type': 'class_based'}
                    
                    # 배경 이미지 스타일 확인
                    if elem.get('style') and 'background-image' in elem.get('style'):
                        style = elem.get('style')
                        url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
                        if url_match:
                            img_url = url_match.group(1)
                            # 스티커 도메인 확인
                            if any(domain in img_url for domain in self.STICKER_DOMAINS):
                                return {'url': img_url, 'type': 'style_based'}
        
        # 2. data-linkdata 속성으로 찾기 (네이버 블로그 특유의 구조)
        elements_with_linkdata = soup.find_all(attrs={"data-linkdata": True})
        for elem in elements_with_linkdata:
            try:
                linkdata = json.loads(elem.get('data-linkdata'))
                if 'src' in linkdata:
                    img_url = linkdata['src']
                    # 스티커 도메인 확인
                    if any(domain in img_url for domain in self.STICKER_DOMAINS):
                        return {'url': img_url, 'type': 'linkdata_based'}
            except:
                pass
        
        # 3. 이미지 태그 중 스티커 도메인을 가진 것 찾기
        all_images = soup.find_all('img')
        for img in all_images:
            if img.get('src'):
                img_url = img.get('src')
                # 스티커 도메인 확인
                if any(domain in img_url for domain in self.STICKER_DOMAINS):
                    return {'url': img_url, 'type': 'img_based'}
        
        # 4. 배경 이미지 스타일을 가진 모든 요소 확인
        all_elements = soup.find_all(lambda tag: tag.get('style') and 'background-image' in tag.get('style'))
        for elem in all_elements:
            style = elem.get('style')
            url_match = re.search(r'url\([\'"]?(.*?)[\'"]?\)', style)
            if url_match:
                img_url = url_match.group(1)
                # 스티커 도메인 확인
                if any(domain in img_url for domain in self.STICKER_DOMAINS):
                    return {'url': img_url, 'type': 'background_based'}
        
        return None
    
    async def detect_sponsored_content(self, html_content: str, blog_url: str = None) -> SponsorDetectionResult:
        """HTML 콘텐츠에서 협찬 콘텐츠를 감지합니다."""
        indicators = []
        debug_info = {}
        
        # HTML이 없거나 불완전한 경우 직접 크롤링
        if not html_content or len(html_content) < 1000 or "se-sticker" not in html_content:
            if blog_url:
                logger.info(f"HTML이 불완전하여 직접 크롤링합니다: {blog_url}")
                html_content = await self.get_full_blog_content(blog_url)
                
                if not html_content:
                    logger.error("블로그 콘텐츠를 가져오지 못했습니다.")
                    return SponsorDetectionResult(
                        is_sponsored=False,
                        indicators=["블로그 콘텐츠를 가져오지 못했습니다."],
                        debug_info={"error": "블로그 콘텐츠를 가져오지 못했습니다."}
                    )
        
        # HTML 파싱
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. 첫 번째 스티커 추출 및 OCR 처리
        first_sticker = self.extract_first_sticker(soup)
        debug_info['first_sticker'] = first_sticker
        
        if first_sticker:
            logger.info(f"첫 번째 스티커 발견: {first_sticker['url']} (타입: {first_sticker['type']})")
            print(f"첫 번째 스티커 발견: {first_sticker['url']} (타입: {first_sticker['type']})")
            
            # 스티커 이미지 다운로드 및 OCR 처리
            image_data = await self.download_image(first_sticker['url'])
            if image_data:
                ocr_text = await self.extract_text_from_image(image_data)
                logger.info(f"스티커 OCR 결과: {ocr_text}")
                print(f"스티커 OCR 결과: {ocr_text}")
                
                debug_info['sticker_ocr'] = ocr_text
                
                # OCR 결과에서 협찬 키워드 및 패턴 확인
                if ocr_text:
                    # 전체 OCR 텍스트 출력 (디버깅용)
                    print(f">>>>OCR 텍스트 전체: {ocr_text}")
                    
                    # 모든 발견된 패턴과 키워드 저장
                    found_patterns = []
                    
                    # 1. 단일 키워드 확인
                    for keyword in self.SPONSOR_KEYWORDS:
                        if keyword in ocr_text:
                            found_patterns.append({
                                'type': 'keyword',
                                'pattern': keyword,
                                'matched_text': keyword
                            })
                    
                    # 2. 복잡한 패턴 확인
                    for pattern in self.SPONSOR_TEXT_PATTERNS:
                        match = re.search(pattern, ocr_text)
                        if match:
                            matched_text = match.group(0)
                            found_patterns.append({
                                'type': 'pattern',
                                'pattern': pattern,
                                'matched_text': matched_text
                            })
                    
                    # 3. 특수 케이스: "업체" + "지원" 조합 확인 (순서 무관)
                    if "업체" in ocr_text and ("지원" in ocr_text or "제공" in ocr_text):
                        found_patterns.append({
                            'type': 'special_case',
                            'pattern': '업체 + 지원/제공',
                            'matched_text': ocr_text
                        })
                    
                    # 4. 특수 케이스: "후기" + "지원/제공" 조합 확인
                    if "후기" in ocr_text and ("지원" in ocr_text or "제공" in ocr_text):
                        found_patterns.append({
                            'type': 'special_case',
                            'pattern': '후기 + 지원/제공',
                            'matched_text': ocr_text
                        })
                    
                    # 발견된 패턴이 있으면 지표에 추가
                    if found_patterns:
                        for pattern_info in found_patterns:
                            pattern_type = pattern_info['type']
                            pattern = pattern_info['pattern']
                            matched_text = pattern_info['matched_text']
                            
                            indicator_text = f"스티커 OCR에서 협찬 {pattern_type} 발견: '{matched_text}' (패턴: {pattern}, 이미지: {first_sticker['url']})"
                            indicators.append(indicator_text)
                            logger.info(indicator_text)
                        
                        # 디버깅 정보에 발견된 패턴 추가
                        debug_info['found_patterns'] = found_patterns
            else:
                logger.warning("스티커 이미지를 다운로드할 수 없습니다.")
                print("스티커 이미지를 다운로드할 수 없습니다.")
        else:
            logger.warning("스티커를 찾을 수 없습니다.")
            print("스티커를 찾을 수 없습니다.")
            debug_info['first_sticker'] = None
        
        # 2. 특정 HTML 구조 패턴 확인 (정확한 패턴만 사용)
        sponsor_elements = []
        for pattern in self.SPONSOR_CLASS_PATTERNS:
            elements = soup.find_all(class_=re.compile(pattern))
            for elem in elements:
                # 협찬과 무관한 클래스를 가진 요소 제외
                elem_classes = ' '.join(elem.get('class', []))
                if not any(re.search(non_pattern, elem_classes) for non_pattern in self.NON_SPONSOR_CLASS_PATTERNS):
                    sponsor_elements.append(elem)
        
        if sponsor_elements:
            # 각 요소의 클래스와 텍스트 정보 추가
            sponsor_element_details = []
            for elem in sponsor_elements:
                elem_class = elem.get('class', [])
                elem_text = elem.get_text(strip=True)[:100]  # 텍스트가 너무 길면 자름
                sponsor_element_details.append({
                    'class': ' '.join(elem_class) if isinstance(elem_class, list) else elem_class,
                    'text': elem_text if elem_text else '(텍스트 없음)'
                })
            
            if sponsor_element_details:
                indicators.append(f"협찬 관련 HTML 요소 발견: {len(sponsor_element_details)}개")
                for i, detail in enumerate(sponsor_element_details, 1):
                    indicators.append(f"  {i}. 클래스: {detail['class']}, 텍스트: {detail['text']}")
                logger.info(f"협찬 관련 HTML 요소 발견: {len(sponsor_element_details)}개")
        
        # 결과 반환
        is_sponsored = len(indicators) > 0
        logger.info(f"협찬 감지 결과: {is_sponsored}, 지표 수: {len(indicators)}")
        
        # 디버깅 정보 추가
        debug_info['is_sponsored'] = is_sponsored
        debug_info['indicators'] = indicators
        
        return SponsorDetectionResult(
            is_sponsored=is_sponsored,
            indicators=indicators,
            debug_info=debug_info
        )