from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Sponsor Filter"
    
    # CORS 설정
    CORS_ORIGINS: List[str] = ["*"]
    
    # 네이버 API 설정
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""
    
    # 필터링 설정
    SPONSOR_KEYWORDS: List[str] = [
        "체험단", "협찬", "제공받아", "원고료", "소정의", "revu", 
        "제작비", "지원받아", "무상제공", "무료체험"
    ]
    
    # 이미지 URL 패턴
    SPONSOR_IMAGE_URLS: List[str] = [
        "cometoplay.kr/data/editor"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 