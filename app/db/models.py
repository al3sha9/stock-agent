import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

class Watchlist(Base):
    """
    Model for tracking stock symbols and target thresholds.
    """
    __tablename__ = "watchlist"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    telegram_chat_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    drop_trigger: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("ticker", "telegram_chat_id", name="uix_ticker_user_chat_id"),
    )

    # Relationships
    trigger_events: Mapped[list["TriggerEvent"]] = relationship(
        "TriggerEvent", back_populates="watchlist", cascade="all, delete-orphan"
    )

class TriggerEvent(Base):
    """
    Model for logging when a stock price triggers an alert.
    """
    __tablename__ = "trigger_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlist.id", ondelete="CASCADE"), nullable=False
    )
    price_at_trigger: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    intrinsic_value: Mapped[float] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str] = mapped_column(String, nullable=True)

    # Relationships
    watchlist: Mapped["Watchlist"] = relationship("Watchlist", back_populates="trigger_events")
