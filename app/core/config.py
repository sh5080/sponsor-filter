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
    
    # OCR 관련 설정
    TESSERACT_DATA_PATH: str = "tessdata"
    
    # 이미지 URL 패턴
    SPONSOR_IMAGE_URLS: List[str] = [
        "cometoplay.kr/data/editor"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 