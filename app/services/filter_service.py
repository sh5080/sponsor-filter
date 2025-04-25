from typing import Dict, List
from app.services.naver_service import NaverService
from app.services.detection_service import DetectionService
from app.services.pattern_analyzer_service import PatternAnalyzerService
from app.models.schemas import BlogPost, SearchResponse, SearchRequest
from app.core.constants import PATTERN_TYPE_WEIGHTS, SOURCE_WEIGHTS
import asyncio
import logging

logger = logging.getLogger(__name__)


class FilterService:
    """네이버 블로그 검색 결과에서 협찬 콘텐츠를 필터링하는 서비스"""
    
    def __init__(self):
        self.naver_service = NaverService()
        self.detection_service = DetectionService()
        self.pattern_analyzer = PatternAnalyzerService()
        # 동시 요청 제한 (서버 부하 및 차단 방지)
        self.semaphore = asyncio.Semaphore(5)  # 최대 5개 요청 동시 처리

    async def process_blog_post(self, item: Dict) -> BlogPost:
        """단일 블로그 포스트를 처리합니다."""
        # 세마포어를 사용해 동시 요청 제한
        async with self.semaphore:
            try:
                # 1. description에서 협찬 문구 확인 (스니펫 텍스트) - 즉시 처리 가능
                description_indicators = self.pattern_analyzer.check_text_for_sponsors(
                    item["description"]
                )

                # 블로그 본문을 가져올 필요가 있는지 먼저 확인
                # description에서 이미 협찬이 감지되면 본문 가져오기 건너뛰기 옵션
                skip_content_check = (
                    bool(description_indicators) and len(description_indicators) >= 2
                )

                # 2. 필요한 경우에만 본문 콘텐츠 가져오기
                html_content = None
                detection_result = None

                if not skip_content_check:
                    # 블로그 콘텐츠 가져오기
                    html_content = await self.naver_service.get_blog_content(
                        item["link"]
                    )

                    # 협찬 여부 감지 (본문)
                    detection_result = (
                        await self.detection_service.detect_sponsored_content(
                            html_content=html_content, blog_url=item["link"]
                        )
                    )

                    # 본문과 설명 모두에서 발견된 지표 병합
                    all_indicators = (
                        detection_result.indicators + description_indicators
                    )
                    is_sponsored = detection_result.is_sponsored or bool(
                        description_indicators
                    )
                else:
                    # description만으로 협찬 판단
                    logger.info(
                        f"Description에서 협찬 감지됨, 본문 처리 건너뜀: {item['link']}"
                    )
                    all_indicators = description_indicators
                    is_sponsored = True

                # 포스트별 협찬 확률 계산 (모든 지표 기반)
                post_probability = self.calculate_sponsor_probability(all_indicators)

                # 결과 생성
                post = BlogPost(
                    title=item["title"],
                    link=item["link"],
                    description=item["description"],
                    bloggername=item["bloggername"],
                    bloggerlink=item["bloggerlink"],
                    postdate=item["postdate"],
                    is_sponsored=is_sponsored,
                    sponsor_indicators=all_indicators,
                    sponsor_probability=post_probability,
                )

                return post
            except Exception as e:
                logger.error(
                    f"블로그 포스트 처리 중 오류: {item['link']}, 오류: {str(e)}"
                )
                # 오류 발생 시 기본 포스트 반환
                return BlogPost(
                    title=item["title"],
                    link=item["link"],
                    description=item["description"],
                    bloggername=item["bloggername"],
                    bloggerlink=item["bloggerlink"],
                    postdate=item["postdate"],
                    is_sponsored=False,
                    sponsor_indicators=[],
                    sponsor_probability=0,
                )
    
    async def search_and_filter(self, request: SearchRequest) -> SearchResponse:
        """
        키워드로 검색하고 협찬 콘텐츠를 필터링합니다.
        
        Args:
            request: 검색 요청 정보
            
        Returns:
            필터링된 검색 결과
        """
        # 네이버 API로 검색 결과 가져오기
        start = (request.page - 1) * request.items_per_page + 1
        search_result = await self.naver_service.search_blogs(
            request.keyword, start=start, display=request.items_per_page
        )

        total_results = search_result.get("total", 0)
        items = search_result.get("items", [])

        # 비어있는 결과 처리
        if not items:
            return SearchResponse(
                keyword=request.keyword,
                total_results=total_results,
                filtered_results=0,
                page=request.page,
                items_per_page=request.items_per_page,
                posts=[],
            )

        # 모든 블로그 포스트 병렬 처리
        tasks = [self.process_blog_post(item) for item in items]
        posts = await asyncio.gather(*tasks)

        # 협찬 포스트 수 계산
        sponsored_count = sum(1 for post in posts if post.is_sponsored)

        # 응답 생성
        response = SearchResponse(
            keyword=request.keyword,
            total_results=total_results,
            filtered_results=sponsored_count,
            page=request.page,
            items_per_page=request.items_per_page,
            posts=posts,
        )

        return response

    def calculate_sponsor_probability(
        self, found_patterns: List[Dict[str, str]]
    ) -> float:
        if not found_patterns:
            return 0.0

        # 모든 소스와 패턴 유형을 결합
        all_weights = {**PATTERN_TYPE_WEIGHTS, **SOURCE_WEIGHTS}

        # 중복 패턴 제거 (같은 패턴과 유형이 여러 번 감지된 경우)
        unique_patterns = {}
        for pattern in found_patterns:
            pattern_key = (
                f"{pattern.get('type', 'unknown')}:{pattern.get('pattern', '')}"
            )

            # 이미 존재하는 패턴이면 소스가 더 신뢰할 수 있는 경우만 업데이트
            if pattern_key in unique_patterns:
                current_source = pattern.get("source", "unknown")

                # OCR 및 스티커는 가장 신뢰할 수 있는 소스 (우선순위 증가)
                if "ocr" in current_source.lower() or "image" in current_source.lower():
                    unique_patterns[pattern_key] = pattern
                    continue

                # 스티커도 높은 가중치 유지
                if "sticker" in current_source.lower():
                    unique_patterns[pattern_key] = pattern
                    continue

            unique_patterns[pattern_key] = pattern

        # 고유한 패턴만 사용
        unique_pattern_list = list(unique_patterns.values())

        # 각 패턴의 확률 값 추출
        pattern_probabilities = []
        for pattern in unique_pattern_list:
            logger.info(f"패턴: {pattern}")
            # 패턴에 직접 확률 값이 있으면 그 값을 사용
            if "probability" in pattern:
                pattern_probabilities.append(pattern["probability"])
                continue
                
            # 없으면 패턴 유형과 소스에 따른 가중치 사용
            pattern_type = pattern.get("type", "unknown")
            source = pattern.get("source", "unknown")

            # 패턴 유형 가중치
            type_weight = all_weights.get(pattern_type, 0.5)
            # 소스 가중치
            source_weight = all_weights.get(source, 0.5)

            logger.info(f"패턴 유형: {pattern_type}, 소스: {source}, 가중치: {type_weight}, {source_weight}")
            # 둘 중 더 높은 가중치 사용
            probability = max(type_weight, source_weight)
            pattern_probabilities.append(probability)

        # 가중치가 없으면 0 반환
        if not pattern_probabilities:
            return 0.0
        
        # 최대 확률 값 사용
        max_probability = max(pattern_probabilities)
        logger.info(f"최대 협찬 확률: {max_probability:.2f} (패턴 수: {len(pattern_probabilities)})")

        # 여러 패턴이 발견된 경우 추가 가중치 부여 (최대 0.95까지)
        if len(pattern_probabilities) > 1:
            # 패턴 수에 따라 가중치 증가 (최대 0.15 추가)
            bonus = min(0.05 * (len(pattern_probabilities) - 1), 0.15)
            max_probability = min(max_probability + bonus, 0.95)
            logger.info(f"여러 패턴 발견으로 인한 보너스 적용 후 확률: {max_probability:.2f} (보너스: +{bonus:.2f})")

        return max_probability
