from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional
import uuid

from app.db.models import Watchlist, TriggerEvent
from app.schemas.stock import WatchlistCreate, WatchlistUpdate

async def get_active_watchlist(db: AsyncSession) -> List[Watchlist]:
    """
    Retrieve all active watchlist items.
    """
    result = await db.execute(
        select(Watchlist).where(Watchlist.is_active == True)
    )
    return list(result.scalars().all())

async def get_user_watchlist(db: AsyncSession, chat_id: str) -> List[Watchlist]:
    """
    Retrieve all watchlist items for a specific user.
    """
    result = await db.execute(
        select(Watchlist).where(Watchlist.telegram_chat_id == chat_id)
    )
    return list(result.scalars().all())

async def get_watchlist_item_by_ticker(db: AsyncSession, ticker: str, chat_id: str) -> Optional[Watchlist]:
    """
    Retrieve a watchlist item by its ticker symbol and telegram_chat_id.
    """
    result = await db.execute(
        select(Watchlist).where(Watchlist.ticker == ticker, Watchlist.telegram_chat_id == chat_id)
    )
    return result.scalars().first()

async def create_watchlist_item(db: AsyncSession, item_in: WatchlistCreate) -> Watchlist:
    """
    Create a new watchlist item.
    """
    db_item = Watchlist(**item_in.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def update_watchlist_item(
    db: AsyncSession, db_item: Watchlist, item_in: WatchlistUpdate
) -> Watchlist:
    """
    Update an existing watchlist item.
    """
    update_data = item_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)
    
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

async def remove_watchlist_item(db: AsyncSession, ticker: str, chat_id: str) -> bool:
    """
    Remove a watchlist item by ticker symbol for a specific user.
    Returns True if deleted, False otherwise.
    """
    result = await db.execute(
        delete(Watchlist).where(Watchlist.ticker == ticker, Watchlist.telegram_chat_id == chat_id)
    )
    await db.commit()
    return result.rowcount > 0

async def deactivate_watchlist_item(db: AsyncSession, ticker: str, chat_id: str) -> bool:
    """
    Deactivate a watchlist item instead of deleting it.
    """
    result = await db.execute(
        update(Watchlist)
        .where(Watchlist.ticker == ticker, Watchlist.telegram_chat_id == chat_id)
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount > 0

async def log_trigger_event(
    db: AsyncSession, watchlist_id: uuid.UUID, price: float
) -> TriggerEvent:
    """
    Log a trigger event when a price target is hit.
    """
    event = TriggerEvent(watchlist_id=watchlist_id, price_at_trigger=price)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event

async def get_last_trigger_event(db: AsyncSession, watchlist_id: uuid.UUID) -> Optional[TriggerEvent]:
    """
    Get the most recent trigger event for a specific watchlist item.
    Used for cooldown checks.
    """
    result = await db.execute(
        select(TriggerEvent)
        .where(TriggerEvent.watchlist_id == watchlist_id)
        .order_by(TriggerEvent.timestamp.desc())
        .limit(1)
    )
    return result.scalars().first()

async def get_trigger_events(db: AsyncSession, chat_id: str) -> List[TriggerEvent]:
    """
    Retrieve all trigger events for a specific user, ordered by timestamp descending.
    """
    result = await db.execute(
        select(TriggerEvent)
        .join(Watchlist)
        .where(Watchlist.telegram_chat_id == chat_id)
        .order_by(TriggerEvent.timestamp.desc())
    )
    return list(result.scalars().all())

async def update_trigger_event_analysis(
    db: AsyncSession, event_id: uuid.UUID, intrinsic_value: float, recommendation: str
) -> Optional[TriggerEvent]:
    """
    Update a trigger event with agent analysis findings.
    """
    result = await db.execute(
        select(TriggerEvent).where(TriggerEvent.id == event_id)
    )
    event = result.scalars().first()
    if event:
        event.intrinsic_value = intrinsic_value
        event.recommendation = recommendation
        await db.commit()
        await db.refresh(event)
    return event
