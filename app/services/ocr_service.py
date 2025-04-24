from pathlib import Path
import os
import hashlib
import tempfile
import logging
import re
import pytesseract  # type: ignore
import aiohttp  # type: ignore
from aiohttp import ClientTimeout  # type: ignore

# 캐시 디렉토리 설정
CACHE_DIR = Path(os.path.join(os.path.dirname(__file__), "../../cache"))
if not CACHE_DIR.exists():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
TESSDATA_PATH = os.path.join(PROJECT_ROOT, "tessdata")

# Tesseract 환경 변수 설정 (아직 설정되지 않은 경우에만)
if not os.environ.get("TESSDATA_PREFIX") and os.path.exists(TESSDATA_PATH):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH
    logger.info(f"TESSDATA_PREFIX 환경 변수를 {TESSDATA_PATH}로 설정했습니다.")


class OCRService:
    """OCR 관련 기능을 제공하는 서비스 클래스"""

    # OCR 결과 캐싱
    ocr_cache = {}

    @staticmethod
    def get_image_cache_path(image_url: str) -> Path:
        """이미지 URL에 대한 캐시 파일 경로를 생성합니다."""
        # URL에서 해시 생성
        hash_obj = hashlib.md5(image_url.encode("utf-8"))
        hash_str = hash_obj.hexdigest()
        return CACHE_DIR / f"ocr_{hash_str}.txt"

    @staticmethod
    def cache_ocr_result(image_url: str, ocr_text: str) -> None:
        """OCR 결과를 캐시에 저장합니다."""
        cache_path = OCRService.get_image_cache_path(image_url)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(ocr_text)
        OCRService.ocr_cache[image_url] = ocr_text

    @staticmethod
    def get_cached_ocr_result(image_url: str) -> str | None:
        """캐시된 OCR 결과를 가져옵니다."""
        # 1. 메모리 캐시 확인
        if image_url in OCRService.ocr_cache:
            return OCRService.ocr_cache[image_url]

        # 2. 파일 캐시 확인
        cache_path = OCRService.get_image_cache_path(image_url)
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    ocr_text = f.read()
                # 메모리 캐시에도 저장
                OCRService.ocr_cache[image_url] = ocr_text
                return ocr_text
            except Exception as e:
                logger.warning(f"캐시 파일 읽기 오류: {str(e)}")
        return None

    @staticmethod
    async def download_image(image_url: str) -> bytes | None:
        """이미지 URL에서 이미지를 다운로드합니다."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "Referer": "https://m.blog.naver.com/",
                "Accept": "image/avif,image/webp,*/*",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
            }
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    image_url, timeout=ClientTimeout(total=5)
                ) as response:  # ClientTimeout 객체 사용
                    if response.status == 200:
                        logger.info(f"이미지 다운로드 성공: {image_url}")
                        return await response.read()
                    else:
                        logger.warning(
                            f"이미지 다운로드 실패: {image_url}, 상태 코드: {response.status}"
                        )
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
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # 1단계: 빠른 OCR 먼저 시도
                text = pytesseract.image_to_string(
                    temp_file_path, lang="kor", config="--psm 1 --oem 1"
                )
                text = re.sub(r"\s+", " ", text).strip()
                
                # 결과가 없으면 정확한 OCR 시도
                if not text:
                    logger.info("첫 번째 OCR 시도 실패, 정확도 높은 설정으로 재시도")
                    text = pytesseract.image_to_string(
                        temp_file_path, 
                        lang="kor", 
                        config="--psm 6 --oem 3 -c preserve_interword_spaces=1"
                    )
                    text = re.sub(r"\s+", " ", text).strip()
                
                logger.info(f"OCR 결과: {text}")
                
            except Exception as e:
                logger.warning(f"OCR 처리 중 오류 발생: {str(e)}")
                text = ""
            
            # 임시 파일 삭제
            os.unlink(temp_file_path)
            
            return text
            
        except Exception as e:
            logger.error(f"이미지에서 텍스트 추출 중 오류 발생: {str(e)}")
            return ""

    @staticmethod
    def normalize_image_url(img_url: str) -> str:
        """이미지 URL을 정규화하여 최상의 품질로 변환합니다."""
        if not img_url:
            return img_url

        # 1. w80_blur 같은 축소/흐림 효과가 있는 URL 수정
        if "?type=w80_blur" in img_url:
            # 네이버 블로그의 경우 type 파라미터 변경
            img_url = img_url.replace("?type=w80_blur", "?type=w773")

        # 2. mblogthumb-phinf를 postfiles로 변환 (썸네일 URL을 원본 URL로 변환)
        if "mblogthumb-phinf.pstatic.net" in img_url:
            img_url = img_url.replace(
                "mblogthumb-phinf.pstatic.net", "postfiles.pstatic.net"
            )

            # 축소된 이미지 파라미터 제거
            if "?type=" in img_url and img_url.count("?") == 1:
                img_url = img_url.replace("?type=w80_blur", "").replace("?type=w80", "")

                # 다른 크기 파라미터가 있는 경우 높은 화질로 변경
                if "?type=w" in img_url:
                    # w뒤의 숫자 추출
                    match = re.search(r"\?type=w(\d+)", img_url)
                    if match and int(match.group(1)) < 500:
                        img_url = img_url.replace(match.group(0), "?type=w773")
        logger.info(f"정규화된 이미지 URL: {img_url}")
        return img_url

    async def process_image_ocr(self, image_url: str) -> str:
        """이미지 URL에서 텍스트를 추출합니다 (캐싱 지원)."""
        # 1. 캐시 확인
        cached_text = self.get_cached_ocr_result(image_url)
        if cached_text is not None:
            logger.info(f"캐시된 OCR 결과 사용: {image_url}")
            return cached_text

        # 2. 이미지 다운로드 및 OCR 처리
        image_data = await self.download_image(image_url)
        if not image_data:
            return ""

        ocr_text = await self.extract_text_from_image(image_data)

        # 3. 결과 캐싱
        if ocr_text:
            self.cache_ocr_result(image_url, ocr_text)

        return ocr_text 