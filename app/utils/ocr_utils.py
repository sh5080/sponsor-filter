"""
OCR 관련 유틸리티 함수들을 제공하는 모듈입니다.
이미지 처리, OCR 텍스트 추출, 캐싱 등의 기능을 포함합니다.
"""

import pytesseract  # type: ignore
import tempfile
import os
import hashlib
import logging
from pathlib import Path
import re

# 로깅 설정
logger = logging.getLogger(__name__)

# 캐시 디렉토리 설정
CACHE_DIR = Path(os.path.join(os.path.dirname(__file__), "../../cache"))
if not CACHE_DIR.exists():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Tesseract 환경 설정
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
TESSDATA_PATH = os.path.join(PROJECT_ROOT, "tessdata")

# Tesseract 환경 변수 설정 (아직 설정되지 않은 경우에만)
if not os.environ.get("TESSDATA_PREFIX") and os.path.exists(TESSDATA_PATH):
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH
    logger.info(f"TESSDATA_PREFIX 환경 변수를 {TESSDATA_PATH}로 설정했습니다.")

# OCR 결과 캐싱
ocr_cache = {}

def get_image_cache_path(image_url: str) -> Path:
    """이미지 URL에 대한 캐시 파일 경로를 생성합니다."""
    # URL에서 해시 생성
    hash_obj = hashlib.md5(image_url.encode("utf-8"))
    hash_str = hash_obj.hexdigest()
    return CACHE_DIR / f"ocr_{hash_str}.txt"

def cache_ocr_result(image_url: str, ocr_text: str) -> None:
    """OCR 결과를 캐시에 저장합니다."""
    cache_path = get_image_cache_path(image_url)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(ocr_text)
    ocr_cache[image_url] = ocr_text

def get_cached_ocr_result(image_url: str) -> str | None:
    """캐시된 OCR 결과를 가져옵니다."""
    # 1. 메모리 캐시 확인
    if image_url in ocr_cache:
        return ocr_cache[image_url]

    # 2. 파일 캐시 확인
    cache_path = get_image_cache_path(image_url)
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ocr_text = f.read()
            # 메모리 캐시에도 저장
            ocr_cache[image_url] = ocr_text
            return ocr_text
        except Exception as e:
            logger.warning(f"캐시 파일 읽기 오류: {str(e)}")
    return None

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
            # OCR 수행 옵션 최적화 - 속도와 정확도 간 균형
            # PSM 모드 1: 자동 페이지 분할 및 OSD
            # OEM 모드 1: LSTM 엔진만 사용 (더 빠름)
            text = pytesseract.image_to_string(
                temp_file_path, lang="kor", config="--psm 1 --oem 1"
            )
        except Exception as e:
            logger.warning(f"한국어 OCR 실패, 기본 OCR로 대체: {str(e)}")
            # 기본 OCR로 대체 (더 빠른 설정)
            text = pytesseract.image_to_string(
                temp_file_path, config="--psm 1 --oem 1"
            )
        
        # 임시 파일 삭제
        os.unlink(temp_file_path)
        
        # 텍스트 정리 (줄바꿈, 여러 공백 등 처리)
        text = re.sub(r"\s+", " ", text).strip()
        
        return text
    except Exception as e:
        logger.error(f"이미지에서 텍스트 추출 중 오류 발생: {str(e)}")
        return ""

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

    return img_url 