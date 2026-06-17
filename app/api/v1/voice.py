"""Голосовой API.

Эндпоинты:
- POST /voice/converse  — основной для колонки/приложения. WAV in → стрим WAV TTS,
                          метаданные пайплайна — в заголовке X-Pipeline-Metadata
                          (base64 JSON, чтобы пройти HTTP).
- POST /voice/stt       — только распознавание (для аналитики/отладки).
- POST /voice/tts       — только синтез (text → WAV stream).
- POST /voice/nlu       — классификация интента по тексту.
- POST /voice/nli/sentiment — тональность.
- POST /voice/nli/entailment — entailment по паре (premise, hypothesis).
- POST /voice/emergency — явная тревога без аудио (от мобильного клиента).

Авторизация — единый user-JWT (та же `get_current_user`, что и для остальных API).
"""
from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.voice import (
    ConverseMetadata,
    EntailmentRequest,
    EntailmentResponse,
    NLURequest,
    NLUResponse,
    SentimentRequest,
    SentimentResponse,
    STTResponse,
    TTSRequest,
)
from app.services.audio_utils import AudioError, save_wav
from app.services.emergency_service import notify_family_of_emergency
from app.services.nli_service import get_nli_service
from app.services.nlu_service import NLUService
from app.services.stt_service import get_stt_service
from app.services.tts_service import get_tts_service
from app.services.voice_pipeline import VoicePipeline

router = APIRouter()


@router.post("/converse")
async def converse(
    audio: UploadFile = File(..., description="WAV PCM 16kHz mono 16-bit"),
    source: str = "speaker",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await audio.read()
    pipeline = VoicePipeline(db, current_user, source=source)

    try:
        meta, response_text = await pipeline.process(data)
    except AudioError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    tts = get_tts_service()
    audio_iter = tts.synthesize_stream(response_text)

    meta_b64 = base64.b64encode(
        json.dumps(meta.to_dict(), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    headers = {
        "X-Pipeline-Metadata": meta_b64,
        "X-Intent": meta.intent,
        "X-Is-Emergency": "1" if meta.is_emergency else "0",
        "X-TTS-Sample-Rate": str(tts.sample_rate),
    }
    return StreamingResponse(audio_iter, media_type="audio/wav", headers=headers)


@router.post("/converse_raw")
async def converse_raw(
    request: Request,
    source: str = "speaker",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Тот же /converse, но без multipart: тело запроса — сырые байты WAV.
    Удобно для встраиваемых клиентов (ESP32 и т.п.), где собирать multipart
    дороже, чем просто стримить тело.
    """
    data = await request.body()
    pipeline = VoicePipeline(db, current_user, source=source)
    try:
        meta, response_text = await pipeline.process(data)
    except AudioError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    tts = get_tts_service()
    audio_iter = tts.synthesize_stream(response_text)
    meta_b64 = base64.b64encode(
        json.dumps(meta.to_dict(), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    headers = {
        "X-Pipeline-Metadata": meta_b64,
        "X-Intent": meta.intent,
        "X-Is-Emergency": "1" if meta.is_emergency else "0",
        "X-TTS-Sample-Rate": str(tts.sample_rate),
    }
    return StreamingResponse(audio_iter, media_type="audio/wav", headers=headers)


@router.post("/stt", response_model=STTResponse)
async def stt_endpoint(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    data = await audio.read()
    try:
        path, duration = save_wav(current_user.id, data)
    except AudioError as e:
        raise HTTPException(status_code=400, detail=str(e))

    res = await get_stt_service().transcribe_file(str(path))
    return STTResponse(
        text=res.text,
        language=res.language,
        confidence=res.confidence,
        duration_sec=res.duration_sec or duration,
    )


@router.post("/tts")
async def tts_endpoint(
    body: TTSRequest,
    current_user: User = Depends(get_current_user),
):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Пустой текст")
    tts = get_tts_service()
    return StreamingResponse(
        tts.synthesize_stream(body.text),
        media_type="audio/wav",
        headers={"X-TTS-Sample-Rate": str(tts.sample_rate)},
    )


@router.post("/nlu", response_model=NLUResponse)
async def nlu_endpoint(
    body: NLURequest,
    current_user: User = Depends(get_current_user),
):
    res = await NLUService().classify(body.text)
    return NLUResponse(
        intent=res.intent,
        slots=res.slots,
        confidence=res.confidence,
        source=res.source,
    )


@router.post("/nli/sentiment", response_model=SentimentResponse)
async def sentiment_endpoint(
    body: SentimentRequest,
    current_user: User = Depends(get_current_user),
):
    res = await get_nli_service().sentiment(body.text)
    return SentimentResponse(label=res.label, score=res.score)


@router.post("/nli/entailment", response_model=EntailmentResponse)
async def entailment_endpoint(
    body: EntailmentRequest,
    current_user: User = Depends(get_current_user),
):
    res = await get_nli_service().entailment(body.premise, body.hypothesis)
    return EntailmentResponse(label=res.label, score=res.score)


@router.post("/emergency")
async def emergency_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Кнопка SOS из мобильного приложения (без аудио)."""
    notified = notify_family_of_emergency(db, current_user, message="manual SOS")
    return {"ok": True, "notified": notified}
