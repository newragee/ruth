from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, JSON, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class VoiceLog(Base):
    __tablename__ = "voice_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    audio_path = Column(String, nullable=True)
    duration_sec = Column(Float, nullable=True)

    transcript = Column(Text, nullable=True)
    stt_language = Column(String, nullable=True)
    stt_confidence = Column(Float, nullable=True)

    nlu_intent = Column(String, nullable=True, index=True)
    nlu_slots = Column(JSON, nullable=True)

    sentiment_label = Column(String, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    entailment_label = Column(String, nullable=True)
    entailment_score = Column(Float, nullable=True)

    response_text = Column(Text, nullable=True)
    is_emergency = Column(Boolean, nullable=False, server_default="false")
    source = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
