import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict

class WatchlistBase(BaseModel):
    """
    Base properties for a watchlist item.
    """
    ticker: str = Field(..., description="Stock ticker symbol (e.g. AAPL)")
    target_price: float = Field(..., gt=0)
    drop_trigger: float = Field(..., gt=0)
    is_active: bool = True
    telegram_chat_id: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_uppercase(cls, v: str) -> str:
        """
        Ensure ticker symbols are always stored in uppercase.
        """
        return v.upper().strip()

class WatchlistCreate(WatchlistBase):
    """
    Schema for creating a new watchlist item.
    """
    pass

class WatchlistUpdate(BaseModel):
    """
    Schema for updating an existing watchlist item.
    """
    ticker: Optional[str] = None
    target_price: Optional[float] = None
    drop_trigger: Optional[float] = None
    is_active: Optional[bool] = None

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_uppercase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.upper().strip()
        return v

class WatchlistRead(WatchlistBase):
    """
    Schema for reading a watchlist item from the database.
    """
    id: uuid.UUID
    
    model_config = ConfigDict(from_attributes=True)

class TriggerEventRead(BaseModel):
    """
    Schema for reading trigger events.
    """
    id: uuid.UUID
    watchlist_id: uuid.UUID
    price_at_trigger: float
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
