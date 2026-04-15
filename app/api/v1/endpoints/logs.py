from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.session import get_db
from app.db import crud
from app.schemas.stock import TriggerEventRead

router = APIRouter()

@router.get("/triggers", response_model=List[TriggerEventRead])
async def read_trigger_events(db: AsyncSession = Depends(get_db)):
    """
    Retrieve the history of all triggered events, ordered by newest first.
    """
    return await crud.get_trigger_events(db)
