from pydantic import BaseModel, HttpUrl, AnyUrl, Field
from typing import List, Optional, Dict, Any, Union

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
    sponsor_indicators: List[str] = []

class SearchResponse(BaseModel):
    keyword: str
    total_results: int
    filtered_results: int
    page: int
    items_per_page: int
    posts: List[BlogPost]
    
class SponsorDetectionResult(BaseModel):
    is_sponsored: bool
    indicators: List[str] = []
    debug_info: Dict = Field(default_factory=dict) 