from pydantic import BaseModel  # type: ignore
from typing import List, Optional, Dict, Any


class SearchRequest(BaseModel):
    keyword: str
    page: int = 1
    items_per_page: int = 10


class BlogPost(BaseModel):
    title: str
    link: str
    description: str
    bloggername: str
    bloggerlink: str
    postdate: str
    is_sponsored: bool = False
    sponsor_probability: float = 0.0  # 협찬일 확률 (0~1 사이 값)
    sponsor_indicators: List[Dict[str, Any]] = []  # 구조화된 지표만 사용


class SearchResponse(BaseModel):
    keyword: str
    total_results: int
    filtered_results: int
    page: int
    items_per_page: int
    posts: List[BlogPost]


# 협찬 지표 감지 결과 상세 정보
class SponsorIndicatorDetail(BaseModel):
    type: str  # keyword, pattern, special_case 등
    pattern: str  # 감지된 패턴이나 키워드
    matched_text: str  # 실제 매칭된 텍스트
    source: str  # 'sticker_ocr', 'html_element' 등
    source_info: Optional[Dict[str, Any]] = None  # 이미지 URL 등 추가 정보
    confidence: float = 1.0  # 신뢰도 점수 (향후 확장용)


# 기존 클래스 수정
class SponsorDetectionResult(BaseModel):
    is_sponsored: bool
    indicators: List[Dict[str, Any]]  # 구조화된 지표 정보
    indicators_text: List[str] = []  # 기존 텍스트 형태 지표 (호환성 유지)
    confidence: float = 0.0  # 협찬 콘텐츠일 확률
    debug_info: Optional[Dict[str, Any]] = None
