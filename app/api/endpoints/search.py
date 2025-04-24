from fastapi import APIRouter, Depends, Query, HTTPException # type: ignore

from app.models.schemas import SearchRequest, SearchResponse
from app.services.filter_service import FilterService

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_blogs(
    keyword: str = Query(..., description="검색할 키워드"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    items_per_page: int = Query(10, ge=1, le=100, description="페이지당 항목 수"),
    filter_service: FilterService = Depends(lambda: FilterService()),
):
    """
    네이버 블로그를 검색하고 협찬 콘텐츠를 필터링합니다.
    """
    try:
        request = SearchRequest(
            keyword=keyword, page=page, items_per_page=items_per_page
        )

        result = await filter_service.search_and_filter(request)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")
