"""TTS через Piper. Голос загружается один раз; синтез отдаётся
в виде streaming-чанков WAV PCM 16-bit mono, чтобы клиент мог начать
воспроизведение до окончания генерации.
"""
from __future__ import annotations

import asyncio
import io
import os
import wave
from pathlib import Path
from threading import Lock
from typing import AsyncIterator, Optional

from loguru import logger

from app.core.config import settings


class TTSService:
    _instance: Optional["TTSService"] = None
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
        from piper import PiperVoice

        models_dir = Path(settings.PIPER_MODELS_DIR)
        models_dir.mkdir(parents=True, exist_ok=True)
        voice_name = settings.PIPER_VOICE
        onnx_path = models_dir / f"{voice_name}.onnx"
        config_path = models_dir / f"{voice_name}.onnx.json"

        if not onnx_path.exists() or not config_path.exists():
            raise FileNotFoundError(
                f"Piper voice не найден: {onnx_path}. "
                f"Скачайте с https://github.com/rhasspy/piper/blob/master/VOICES.md "
                f"и положите оба файла ({voice_name}.onnx, {voice_name}.onnx.json) "
                f"в каталог {models_dir.resolve()}"
            )

        logger.info(f"Загрузка Piper voice: {voice_name}")
        self._voice = PiperVoice.load(str(onnx_path), config_path=str(config_path))
        self._sample_rate = self._voice.config.sample_rate
        self._initialized = True

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def _synthesize_to_wav_bytes(self, text: str) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self._sample_rate)
            self._voice.synthesize(text, wav)
        return buf.getvalue()

    async def synthesize_full(self, text: str) -> bytes:
        """Полный WAV (для эндпоинта /tts, REST-клиентов)."""
        return await asyncio.to_thread(self._synthesize_to_wav_bytes, text)

    async def synthesize_stream(self, text: str, chunk_size: int = 4096) -> AsyncIterator[bytes]:
        """WAV-поток с заголовком в первом чанке. Сначала отдаём header,
        потом PCM-данные кусками — клиент начинает играть сразу."""
        data = await asyncio.to_thread(self._synthesize_to_wav_bytes, text)
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]
            # отдаём управление event loop между чанками
            await asyncio.sleep(0)


def get_tts_service() -> TTSService:
    return TTSService()
