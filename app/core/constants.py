"""
스폰서 필터링에 사용되는 상수 및 패턴 정의

모든 패턴과 가중치를 한 곳에서 관리하여 일관성을 유지합니다.
"""

EXACT_SPONSOR_KEYWORDS_PATTERNS = {
    "원고료",
    "소정의",
    "업체",
    "체험단",
    "협찬",
    # ocr로 잘못 읽었지만 협찬 패턴
    "[현산",
    "[.싫헐진",
}

SPECIAL_CASE_PATTERNS = {
            "업체 + 지원/제공": {
                "terms1": ["업체"],
                "terms2": ["지원", "제공"]
            },
            "후기 + 지원/제공": {
                "terms1": ["후기"],
                "terms2": ["지원", "제공"]
            },
            "광고 + 콘텐츠": {
                "terms1": ["광고"],
                "terms2": ["콘텐츠", "포스팅", "게시물"]
            },
            "AD + 포스팅": {
                "terms1": ["ad"],
                "terms2": ["포스팅", "콘텐츠", "게시물"]
            }
        }

# 스폰서 단일 키워드 (모호하고 일반적인 단어일수록 낮은 가중치)
SPONSOR_KEYWORDS = {
    # 협찬 관련 키워드
    "협찬": 0.8,
    "체험단": 0.6,
    "체험": 0.3,
    "지원": 0.4,
    "제공": 0.4,
    "무상": 0.4,
    "무료제공": 0.6,
    # EXACT_SPONSOR_KEYWORDS_PATTERNS 에 있어서 제외함
    # "원고료": 0.9,
    # "소정의": 0.9,
    "고료": 0.6,
    "제품제공": 0.7,
    # 유료 광고 관련 키워드
    "광고": 0.01,
    "유료광고": 0.8,
    # 공통 키워드 (매우 낮은 가중치)
    "작성": 0.01,
    "후기": 0.01,
    "받았습니다": 0.2,
    "받아": 0.01,
    "받고": 0.01,
    "로부터": 0.01,
}

# 스티커 도메인 패턴
STICKER_DOMAINS = [
    "storep-phinf.pstatic.net",
    "post-phinf.pstatic.net",
    "cometoplay.kr",
    "reviewnote.co.kr",
]

# 스티커 클래스 패턴
STICKER_CLASSES = [
    "se-sticker",
    "sticker",
    "_img",
    "sponsor-tag",
    "ad-tag",
    "se-module",
    "se-module-image",
    "se-image-resource",
]

# 협찬 관련 클래스 패턴
SPONSOR_CLASS_PATTERNS = [
    r"sponsor",
    r"ad-tag",
    r"promotion",
    r"체험단",
    r"협찬",
    r"revu",
    r"advertisement",
    r"paid",
    r"ppl",
    r"ad-content",
]

# 패턴 유형별 가중치
PATTERN_TYPE_WEIGHTS = {
    "pattern": 0.8,  # 정규식 패턴 매치 (가장 높은 가중치)
    "special_case": 0.75,  # 특수 케이스 패턴 매치
    "keyword": 0.4,  # 단일 키워드 매치 (낮은 가중치)
    "image_text": 0.7,  # 이미지에서 추출된 텍스트
    "unknown": 0.1,  # 알 수 없는 패턴 유형
}

# 소스 유형별 가중치
SOURCE_WEIGHTS = {
    "sticker_ocr": 0.85,  # 스티커 OCR은 매우 높은 가중치
    "description": 0.8,  # description은 매우 높은 가중치
    "html_element": 0.7,  # HTML 요소는 중간 가중치
    "text_content": 0.3,  # 일반 텍스트 내용은 낮은 가중치
    "unknown": 0.1,  # 알 수 없는 소스는 매우 낮은 가중치
}

