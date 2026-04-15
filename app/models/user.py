import uuid
from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class User(Base):
    """
    User model for Telegram Bot Subscriber RBAC.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_chat_id = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
