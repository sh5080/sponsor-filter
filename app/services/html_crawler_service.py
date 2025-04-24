import logging
import aiohttp  # type: ignore
from aiohttp import ClientTimeout  # type: ignore

logger = logging.getLogger(__name__)

class HTMLCrawlerService:
    """블로그 HTML 콘텐츠를 크롤링하는 서비스 클래스"""
    
    @staticmethod
    async def get_full_blog_content(blog_url: str) -> str | None:
        """블로그 URL에서 전체 HTML 콘텐츠를 가져옵니다."""
        try:
            # 모바일 버전 URL로 변환 (더 단순한 구조)
            if "blog.naver.com" in blog_url and "m.blog.naver.com" not in blog_url:
                blog_url = blog_url.replace("blog.naver.com", "m.blog.naver.com")
            
            # 다양한 User-Agent 설정 (차단 방지)
            headers = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://m.search.naver.com/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
            
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    blog_url, timeout=ClientTimeout(total=5)
                ) as response:  # 타임아웃 수정
                    if response.status == 200:
                        html_content = await response.text()
                        
                        # 차단 여부 확인
                        if (
                            "비정상적인 접근" in html_content
                            or "로봇" in html_content
                            or "자동화된 접근" in html_content
                        ):
                            logger.error(f"네이버에서 차단되었습니다: {blog_url}")
                            return None
                        
                        logger.info(f"블로그 콘텐츠 가져오기 성공: {blog_url}")
                        return html_content
                    else:
                        logger.warning(
                            f"블로그 콘텐츠 가져오기 실패: {blog_url}, 상태 코드: {response.status}"
                        )
                        return None
        except Exception as e:
            logger.error(
                f"블로그 콘텐츠 가져오기 중 오류 발생: {blog_url}, 오류: {str(e)}"
            )
            return None 