from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import search
from app.core.config import settings

app = FastAPI(
    title="Sponsor Filter API",
    description="네이버 블로그 포스트에서 협찬 콘텐츠를 필터링하는 API",
    version="0.1.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(search.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Sponsor Filter API!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 