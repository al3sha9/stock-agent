from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class BaseSchema(BaseModel):
    """
    Base Pydantic model with default configuration.
    """
    model_config = ConfigDict(from_attributes=True)

class StockBase(BaseSchema):
    symbol: str
    name: Optional[str] = None

class StockCreate(StockBase):
    pass

class Stock(StockBase):
    id: int
