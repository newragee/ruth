"""STT через faster-whisper (CTranslate2-бэкенд Whisper).

Модель загружается один раз при первом обращении (singleton),
последующие вызовы переиспользуют её. Это даёт минимальную задержку
для batch-запросов от колонки/приложения с уже нарезанным VAD аудио.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from loguru import logger

from app.core.config import settings


@dataclass
class STTResult:
    text: str
    language: str
    confidence: float
    duration_sec: float


class STTService:
    _instance: Optional["STTService"] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        from faster_whisper import WhisperModel

        logger.info(
            f"Загрузка faster-whisper: model={settings.WHISPER_MODEL} "
            f"device={settings.WHISPER_DEVICE} compute={settings.WHISPER_COMPUTE_TYPE}"
        )
        self._model = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type=settings.WHISPER_COMPUTE_TYPE,
        )
        self._initialized = True

    def _transcribe_sync(self, audio_path: str) -> STTResult:
        # VAD-фильтр на стороне Whisper отрезает паузы → меньше галлюцинаций.
        segments, info = self._model.transcribe(
            audio_path,
            language=settings.WHISPER_LANGUAGE,
            beam_size=1,            # greedy → ниже задержка
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
        )
        parts: list[str] = []
        avg_logprob_sum = 0.0
        n = 0
        for seg in segments:
            parts.append(seg.text.strip())
            avg_logprob_sum += seg.avg_logprob
            n += 1
        text = " ".join(p for p in parts if p).strip()
        confidence = float(min(1.0, max(0.0, (avg_logprob_sum / n + 1.0)))) if n else 0.0
        return STTResult(
            text=text,
            language=info.language or settings.WHISPER_LANGUAGE,
            confidence=confidence,
            duration_sec=float(info.duration or 0.0),
        )

    async def transcribe_file(self, audio_path: str) -> STTResult:
        return await asyncio.to_thread(self._transcribe_sync, audio_path)


def get_stt_service() -> STTService:
    return STTService()
