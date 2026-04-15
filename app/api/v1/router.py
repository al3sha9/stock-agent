from fastapi import APIRouter

from app.api.v1.endpoints import stocks, logs

api_router = APIRouter()

api_router.include_router(stocks.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])

@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
