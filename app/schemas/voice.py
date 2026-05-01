from typing import Any, Optional
from pydantic import BaseModel


class STTResponse(BaseModel):
    text: str
    language: str
    confidence: float
    duration_sec: float


class TTSRequest(BaseModel):
    text: str


class NLURequest(BaseModel):
    text: str


class NLUResponse(BaseModel):
    intent: str
    slots: dict[str, Any] = {}
    confidence: float
    source: str


class SentimentRequest(BaseModel):
    text: str


class SentimentResponse(BaseModel):
    label: str
    score: float


class EntailmentRequest(BaseModel):
    premise: str
    hypothesis: str


class EntailmentResponse(BaseModel):
    label: str
    score: float


class ConverseMetadata(BaseModel):
    transcript: str
    stt_language: str
    stt_confidence: float
    duration_sec: float
    intent: str
    intent_confidence: float
    intent_source: str
    slots: dict[str, Any]
    sentiment_label: str
    sentiment_score: float
    entailment_label: Optional[str] = None
    entailment_score: Optional[float] = None
    response_text: str
    is_emergency: bool
    saved_metrics: list[str] = []
    notified_family_members: int = 0
