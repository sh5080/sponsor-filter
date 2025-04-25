import aiohttp # type: ignore
from typing import Dict, Any
from app.core.config import settings


class NaverService:
    """네이버 API를 사용하여 블로그 검색 결과를 가져오는 서비스"""

    BLOG_SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"

    @staticmethod
    async def search_blogs(
        keyword: str, start: int = 1, display: int = 10
    ) -> Dict[str, Any]:
        """
        네이버 블로그 검색 API를 호출하여 결과를 반환합니다.

        Args:
            keyword: 검색할 키워드
            start: 검색 시작 위치 (페이지네이션)
            display: 한 번에 표시할 검색 결과 개수

        Returns:
            검색 결과 딕셔너리
        """
        headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
        }

        params = {
            "query": keyword,
            "display": display,
            "start": start,
            "sort": "sim",  # 정확도순 정렬
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                NaverService.BLOG_SEARCH_URL, headers=headers, params=params
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"네이버 API 호출 실패: {response.status}, {error_text}"
                    )

    @staticmethod
    async def get_blog_content(url: str) -> str:
        """
        블로그 URL에서 HTML 콘텐츠를 가져옵니다.

        Args:
            url: 블로그 포스트 URL

        Returns:
            HTML 콘텐츠
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    return ""
