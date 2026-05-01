"""Аудио-утилиты: проверка/нормализация WAV в 16kHz mono PCM16."""
from __future__ import annotations

import io
import os
import wave
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


class AudioError(ValueError):
    pass


def ensure_storage_dir(user_id: int) -> Path:
    base = Path(settings.VOICE_STORAGE_DIR) / str(user_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def save_wav(user_id: int, data: bytes) -> tuple[Path, float]:
    """Сохранить WAV-байты на диск, проверив формат.
    Возвращает (путь, длительность_сек).
    """
    if not data or len(data) < 44:
        raise AudioError("Пустой или повреждённый WAV (нет RIFF-заголовка)")

    # Валидация: WAV 16kHz mono PCM16. ffmpeg-конверсия не делается —
    # клиент обязан прислать корректный формат (см. docs).
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels = w.getnchannels()
            sample_rate = w.getframerate()
            sample_width = w.getsampwidth()
            n_frames = w.getnframes()
    except wave.Error as e:
        raise AudioError(f"Невалидный WAV: {e}")

    if channels != 1:
        raise AudioError(f"Ожидается mono (1 канал), получено {channels}")
    if sample_rate != settings.VOICE_SAMPLE_RATE:
        raise AudioError(
            f"Ожидается частота {settings.VOICE_SAMPLE_RATE} Гц, получено {sample_rate}"
        )
    if sample_width != 2:
        raise AudioError(f"Ожидается PCM 16-bit, sample_width={sample_width}")

    duration = n_frames / float(sample_rate) if sample_rate else 0.0
    if duration > 120:
        raise AudioError("Аудио длиннее 120 секунд — отклонено")

    dest = ensure_storage_dir(user_id) / f"{uuid4().hex}.wav"
    dest.write_bytes(data)
    return dest, duration
