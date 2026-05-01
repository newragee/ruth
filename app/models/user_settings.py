from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    address_name = Column(String, nullable=True)
    voice = Column(String, nullable=False, server_default="ru_RU-irina-medium")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
