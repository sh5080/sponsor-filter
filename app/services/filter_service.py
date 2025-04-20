from typing import Dict, List, Any
from app.services.naver_service import NaverService
from app.services.detection_service import DetectionService
from app.models.schemas import BlogPost, SearchResponse, SearchRequest

class FilterService:
    """네이버 블로그 검색 결과에서 협찬 콘텐츠를 필터링하는 서비스"""
    
    def __init__(self):
        self.naver_service = NaverService()
        self.detection_service = DetectionService()
    
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
            request.keyword, 
            start=start, 
            display=request.items_per_page
        )

        total_results = search_result.get('total', 0)
        items = search_result.get('items', [])
        
        # 각 블로그 포스트 분석
        posts = []
        for item in items:
            # 블로그 콘텐츠 가져오기
            html_content = await self.naver_service.get_blog_content(item['link'])
            # 협찬 여부 감지
            detection_result = await self.detection_service.detect_sponsored_content(
                html_content=html_content,
                blog_url=item['link']
            )
            
            # 결과 생성
            post = BlogPost(
                title=item['title'],
                link=item['link'],
                description=item['description'],
                bloggername=item['bloggername'],
                bloggerlink=item['bloggerlink'],
                postdate=item['postdate'],
                is_sponsored=detection_result.is_sponsored,
                sponsor_indicators=detection_result.indicators
            )
            posts.append(post)
        
        # 필터링된 결과 수 계산
        filtered_results = sum(1 for post in posts if post.is_sponsored)
        
        return SearchResponse(
            keyword=request.keyword,
            total_results=total_results,
            filtered_results=filtered_results,
            page=request.page,
            items_per_page=request.items_per_page,
            posts=posts
        ) 