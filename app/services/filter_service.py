from typing import Dict, List, Any
from app.services.naver_service import NaverService
from app.services.detection_service import DetectionService
from app.models.schemas import BlogPost, SearchResponse, SearchRequest
from app.core.constants import (
    SPONSOR_PATTERNS,
    SPECIAL_CASE_PATTERNS,
    SPONSOR_KEYWORDS,
    PATTERN_TYPE_WEIGHTS,
    SOURCE_WEIGHTS,
)
import re
import asyncio
import logging

logger = logging.getLogger(__name__)


class FilterService:
    """네이버 블로그 검색 결과에서 협찬 콘텐츠를 필터링하는 서비스"""
    
    def __init__(self):
        self.naver_service = NaverService()
        self.detection_service = DetectionService()
        # 동시 요청 제한 (서버 부하 및 차단 방지)
        self.semaphore = asyncio.Semaphore(5)  # 최대 5개 요청 동시 처리

    async def process_blog_post(self, item: Dict) -> BlogPost:
        """단일 블로그 포스트를 처리합니다."""
        # 세마포어를 사용해 동시 요청 제한
        async with self.semaphore:
            try:
                # 1. description에서 협찬 문구 확인 (스니펫 텍스트) - 즉시 처리 가능
                description_indicators = self.check_description_for_sponsors(
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

    def check_description_for_sponsors(self, description: str) -> List[Dict[str, Any]]:
        """
        블로그 포스트 description(스니펫)에서 협찬 문구를 확인합니다.

        Args:
            description: 블로그 포스트 description 텍스트

        Returns:
            감지된 협찬 지표 목록
        """
        if not description:
            return []

        found_indicators = []

        # HTML 태그 제거
        clean_text = re.sub(r"<[^>]+>", "", description)

        # 1. 단일 키워드 확인
        for keyword in SPONSOR_KEYWORDS:
            if keyword in clean_text:
                found_indicators.append(
                    {
                        "type": "keyword",
                        "pattern": keyword,
                        "matched_text": keyword,
                        "source": "description",
                        "source_info": {
                            "text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            )
                        },
                    }
                )

        # 2. 복잡한 패턴 확인
        for pattern in SPONSOR_PATTERNS:
            match = re.search(pattern, clean_text)
            if match:
                matched_text = match.group(0)
                found_indicators.append(
                    {
                        "type": "pattern",
                        "pattern": pattern,
                        "matched_text": matched_text,
                        "source": "description",
                        "source_info": {
                            "text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            )
                        },
                    }
                )

        # 3. 특수 케이스 확인
        for special_case in SPECIAL_CASE_PATTERNS:
            if "업체 + 지원/제공" == special_case:
                if "업체" in clean_text and any(
                    term in clean_text for term in ["지원", "제공"]
                ):
                    found_indicators.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            ),
                            "source": "description",
                            "source_info": {
                                "text": (
                                    clean_text[:50] + "..."
                                    if len(clean_text) > 50
                                    else clean_text
                                )
                            },
                        }
                    )
            elif "후기 + 지원/제공" == special_case:
                if "후기" in clean_text and any(
                    term in clean_text for term in ["지원", "제공"]
                ):
                    found_indicators.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            ),
                            "source": "description",
                            "source_info": {
                                "text": (
                                    clean_text[:50] + "..."
                                    if len(clean_text) > 50
                                    else clean_text
                                )
                            },
                        }
                    )
            elif "광고 + 콘텐츠" == special_case:
                if "광고" in clean_text and any(
                    term in clean_text for term in ["콘텐츠", "포스팅", "게시물"]
                ):
                    found_indicators.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            ),
                            "source": "description",
                            "source_info": {
                                "text": (
                                    clean_text[:50] + "..."
                                    if len(clean_text) > 50
                                    else clean_text
                                )
                            },
                        }
                    )
            elif "AD + 포스팅" == special_case:
                if ("AD" in clean_text or "ad" in clean_text.lower()) and any(
                    term in clean_text for term in ["포스팅", "콘텐츠", "게시물"]
                ):
                    found_indicators.append(
                        {
                            "type": "special_case",
                            "pattern": special_case,
                            "matched_text": (
                                clean_text[:50] + "..."
                                if len(clean_text) > 50
                                else clean_text
                            ),
                            "source": "description",
                            "source_info": {
                                "text": (
                                    clean_text[:50] + "..."
                                    if len(clean_text) > 50
                                    else clean_text
                                )
                            },
                        }
                    )

        return found_indicators

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
                existing_source = unique_patterns[pattern_key].get("source", "unknown")

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
        filtered_patterns = list(unique_patterns.values())

        # 학술/정보성 콘텐츠 키워드가 포함된 경우 감지
        academic_keywords = [
            "학술",
            "연구",
            "논문",
            "학회",
            "교육",
            "수업",
            "강의",
            "정보",
            "참고",
            "참조",
            "도서관",
            "자료",
            "문헌",
        ]
        is_academic_context = False
        for pattern in filtered_patterns:
            matched_text = pattern.get("matched_text", "")
            source_info = pattern.get("source_info", {})
            text = source_info.get("text", "")

            for keyword in academic_keywords:
                if keyword in matched_text or (text and keyword in text):
                    is_academic_context = True
                    break

        # 패턴별 가중치 적용
        indicator_prob = 0.0
        max_prob = 0.0
        patterns_list = []

        # 스티커 소스 확인
        has_sticker_source = any(
            "sticker" in p.get("source", "").lower() for p in filtered_patterns
        )

        # OCR 이미지 소스 확인
        has_ocr_source = any(
            (
                "ocr" in p.get("source", "").lower()
                or "image" in p.get("source", "").lower()
            )
            for p in filtered_patterns
        )

        for pattern in filtered_patterns:
            pattern_type = pattern.get("type", "unknown")
            source = pattern.get("source", "unknown")
            pattern_text = pattern.get("pattern", "")

            # 패턴 유형 가중치와 소스 가중치 계산
            type_weight = all_weights.get(pattern_type, 0.2)

            # 소스별 가중치 조정
            source_weight = all_weights.get(source, 0.3)

            # OCR 및 이미지 소스의 가중치 증가
            if "ocr" in source.lower() or "image" in source.lower():
                source_weight = 0.85  # OCR/이미지 소스는 매우 높은 가중치

            # 스티커 소스의 경우도 높은 가중치 유지
            if "sticker" in source.lower():
                source_weight = 0.9  # 스티커 소스는 매우 높은 가중치

            # 학술 컨텍스트인 경우 가중치 감소 (OCR과 스티커 제외)
            if is_academic_context and not (
                "sticker" in source.lower()
                or "ocr" in source.lower()
                or "image" in source.lower()
            ):
                source_weight *= 0.6  # 학술적 맥락에서는 협찬 가능성 40% 감소

            # 패턴 자체의 가중치 가져오기
            content_weight = 0.0

            if pattern_type == "pattern":
                for p, w in SPONSOR_PATTERNS.items():
                    if re.search(p, pattern_text, re.IGNORECASE):
                        content_weight = w
                        break
            elif pattern_type == "special_case":
                for p, w in SPECIAL_CASE_PATTERNS.items():
                    if p in pattern_text or re.search(p, pattern_text, re.IGNORECASE):
                        content_weight = w
                        break
            elif pattern_type == "keyword":
                content_weight = SPONSOR_KEYWORDS.get(pattern_text.lower(), 0.2)

            # 최종 확률 계산 (타입과 소스 가중치 증가, 콘텐츠 가중치 감소)
            # OCR 소스인 경우 소스 가중치 영향력 증가
            if (
                "ocr" in source.lower()
                or "image" in source.lower()
                or "sticker" in source.lower()
            ):
                pattern_prob = (
                    (type_weight * 0.3) + (source_weight * 0.6) + (content_weight * 0.1)
                )
            else:
                pattern_prob = (
                    (type_weight * 0.5) + (source_weight * 0.3) + (content_weight * 0.2)
                )

            # 최대 확률 업데이트
            max_prob = max(max_prob, pattern_prob)

            # 모든 패턴의 확률을 결합
            indicator_prob += pattern_prob
            patterns_list.append(pattern_text)

        # OCR이나 스티커에서 발견된 패턴이 있는 경우 최소 확률 설정
        if has_ocr_source or has_sticker_source:
            min_probability = 0.7  # OCR/스티커가 있으면 최소 70% 이상

            # 리뷰노트 스티커는 100% 확률 지정 (공정위 표시는 명확한 협찬)
            reviewnote_patterns = [
                p
                for p in filtered_patterns
                if (
                    "reviewnote" in p.get("source", "").lower()
                    or (
                        p.get("source_info", {}).get("image_url", "")
                        and "reviewnote"
                        in p.get("source_info", {}).get("image_url", "")
                    )
                )
            ]

            if reviewnote_patterns:
                return 1.0  # 리뷰노트 스티커가 있으면 100% 확률

            # OCR이나 스티커에서 명확한 스폰서 키워드가 발견된 경우
            sponsor_keywords = ["광고", "협찬", "AD", "제공", "Sponsored", "PPL"]
            ocr_sticker_patterns = [
                p
                for p in filtered_patterns
                if (
                    "ocr" in p.get("source", "").lower()
                    or "image" in p.get("source", "").lower()
                    or "sticker" in p.get("source", "").lower()
                )
            ]

            if any(
                p.get("pattern", "").lower() in sponsor_keywords
                for p in ocr_sticker_patterns
            ):
                min_probability = 0.85  # 명확한 스폰서 키워드가 있으면 최소 85%
        else:
            min_probability = 0.0

        # 단일 키워드 케이스 처리
        if (
            len(filtered_patterns) == 1
            and filtered_patterns[0].get("type") == "keyword"
        ):
            pattern_text = filtered_patterns[0].get("pattern", "").lower()
            source = filtered_patterns[0].get("source", "").lower()

            # OCR이나 스티커에서 발견된 키워드는 높은 확률 유지
            if "ocr" in source or "image" in source or "sticker" in source:
                if pattern_text in ["광고", "협찬", "AD", "Sponsored", "PPL"]:
                    return max(min_probability, min(max_prob, 0.9))
                if pattern_text in ["제공", "지원"]:
                    return max(min_probability, min(max_prob, 0.8))
                return max(min_probability, min(max_prob, 0.7))

            # 일반적인 단일 키워드의 경우 최대 확률 제한
            if pattern_text in ["광고", "후기"]:
                return min(max_prob, 0.4)

            # 다른 단일 키워드의 경우 최대 50%로 제한
            return min(max_prob, 0.5)

        # 확률 상한선 설정
        if has_ocr_source or has_sticker_source:
            # OCR이나 스티커에서 발견된 경우, 패턴에 따라 상한선 조정
            # 제공, 지원 같은 일반적 단어만 있는 경우 제한
            general_keywords = ["제공", "지원", "후기", "작성"]
            if all(
                p.get("pattern", "").lower() in general_keywords
                for p in filtered_patterns
            ):
                max_probability = 0.8  # 최대 80%
            else:
                max_probability = 0.95  # 최대 95%
        else:
            max_probability = 0.9  # 일반적인 경우 최대 90%

        # 종합 확률 계산 (여러 패턴이 있는 경우)
        # 정규화 - 패턴 개수가 많을수록 가중치 분산
        normalized_indicator_prob = indicator_prob / (1 + len(filtered_patterns) * 0.2)

        # 패턴 간 중복 가능성을 고려하여 결합 확률 계산
        # OCR이나 스티커가 있으면 max_prob의 영향력 증가
        if has_ocr_source or has_sticker_source:
            combined_prob = normalized_indicator_prob * 0.2 + max_prob * 0.8
        else:
            combined_prob = normalized_indicator_prob * 0.3 + max_prob * 0.7

        # 일반적 키워드만 포함된 경우 확률 제한 (OCR이나 스티커가 없는 경우)
        if not (has_ocr_source or has_sticker_source):
            common_keywords = ["광고", "후기", "제공", "지원", "작성"]
            only_common_keywords = all(
                p.get("pattern", "").lower() in common_keywords
                for p in filtered_patterns
            )

            if only_common_keywords:
                # 키워드 개수에 따른 최대값 제한
                if len(filtered_patterns) == 1:
                    return min(combined_prob, 0.4)  # 단일 키워드 40% 제한
                elif len(filtered_patterns) == 2:
                    return min(combined_prob, 0.6)  # 두 개 키워드 60% 제한
                else:
                    return min(combined_prob, 0.8)  # 여러 키워드 80% 제한

        # 최종 확률 계산 (OCR/스티커 기반 최소 확률 적용)
        return max(min_probability, min(combined_prob, max_probability))
