from fastapi import APIRouter, Depends

from app.api.v1.endpoints import stocks, logs
from app.api.deps import get_api_key

api_router = APIRouter(dependencies=[Depends(get_api_key)])

api_router.include_router(stocks.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])

@api_router.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}
