from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.db.session import get_db
from app.db import crud
from app.schemas.stock import WatchlistCreate, WatchlistRead
from app.services.watcher import watcher_engine

router = APIRouter()

@router.post("/", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
async def add_watchlist_item(item_in: WatchlistCreate, db: AsyncSession = Depends(get_db), x_telegram_chat_id: str = Header(...)):
    """
    Add a new stock ticker to the watchlist for a specific user.
    """
    # Check if already exists
    existing = await crud.get_watchlist_item_by_ticker(db, item_in.ticker, x_telegram_chat_id)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Ticker {item_in.ticker} already exists in watchlist."
        )
    
    item_in.telegram_chat_id = x_telegram_chat_id
    return await crud.create_watchlist_item(db, item_in)

@router.get("/", response_model=List[WatchlistRead])
async def list_watchlist(db: AsyncSession = Depends(get_db), x_telegram_chat_id: str = Header(...)):
    """
    Get all stocks currently in the user's watchlist.
    """
    return await crud.get_user_watchlist(db, x_telegram_chat_id)

@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(ticker: str, db: AsyncSession = Depends(get_db), x_telegram_chat_id: str = Header(...)):
    """
    Remove a stock from the user's watchlist.
    """
    # Ensure ticker is uppercase for lookup
    ticker_upper = ticker.upper().strip()
    deleted = await crud.remove_watchlist_item(db, ticker_upper, x_telegram_chat_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker {ticker_upper} not found in watchlist."
        )
    return None

@router.get("/status", response_model=List[Dict[str, Any]])
async def get_watchlist_status(db: AsyncSession = Depends(get_db), x_telegram_chat_id: str = Header(...)):
    """
    Get a real-time status update for all watched stocks for this user.
    """
    items = await crud.get_user_watchlist(db, x_telegram_chat_id)
    results = []
    
    for item in items:
        data = await watcher_engine.fetch_ticker_data(item.ticker)
        results.append({
            "ticker": item.ticker,
            "target_price": item.target_price,
            "current_price": data.get("last_price") if data["success"] else None,
            "previous_close": data.get("previous_close") if data["success"] else None,
            "status": "online" if data["success"] else "error"
        })
    
    return results
