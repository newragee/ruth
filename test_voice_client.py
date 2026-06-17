"""Минимальный CLI-клиент для проверки голосового пайплайна.

Запись с микрофона → POST /api/v1/voice/converse → проигрывание ответа
+ печать метаданных пайплайна (транскрипт, интент, тональность, ...).

Использование:
    pip install sounddevice soundfile requests numpy
    python test_voice_client.py                       # 5-сек запись
    python test_voice_client.py --duration 8          # 8 секунд
    python test_voice_client.py --wav my_phrase.wav   # без микрофона

Опции:
    --server   адрес сервера (default http://localhost:8000)
    --user     username (создастся автоматически, если нет)
    --password пароль
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import wave
from pathlib import Path

import requests

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPWIDTH = 2  # bytes (16-bit)


def record_from_mic(duration: float) -> bytes:
    import sounddevice as sd
    import numpy as np

    print(f"[mic] Запись {duration:.1f} с — говорите...")
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
    )
    sd.wait()
    print("[mic] Готово.")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPWIDTH)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


def auth(server: str, username: str, password: str) -> str:
    """Логин или регистрация — в обоих случаях вернёт JWT."""
    r = requests.post(
        f"{server}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    if r.status_code == 200:
        return r.json()["access_token"]

    r = requests.post(
        f"{server}/api/v1/auth/register",
        json={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def play_wav(wav_bytes: bytes) -> None:
    import sounddevice as sd
    import soundfile as sf

    out = Path("response.wav")
    out.write_bytes(wav_bytes)
    audio, sr = sf.read(out)
    print(f"[play] Ответ: {len(wav_bytes)} байт, {sr} Гц, {len(audio)/sr:.2f} с")
    sd.play(audio, sr)
    sd.wait()


def pretty_meta(meta: dict) -> None:
    print("\n=== Метаданные пайплайна ===")
    print(f"Транскрипт : {meta['transcript']!r}")
    print(
        f"Интент     : {meta['intent']} "
        f"(conf={meta['intent_confidence']:.2f}, src={meta['intent_source']})"
    )
    if meta.get("slots"):
        print(f"Слоты      : {meta['slots']}")
    print(
        f"Sentiment  : {meta['sentiment_label']} ({meta['sentiment_score']:.2f})"
    )
    if meta.get("entailment_label"):
        print(
            f"Entailment : {meta['entailment_label']} "
            f"({meta['entailment_score']:.2f})"
        )
    print(f"Emergency  : {meta['is_emergency']}")
    if meta.get("saved_metrics"):
        print(f"Сохранено  : {meta['saved_metrics']}")
    if meta.get("notified_family_members"):
        print(f"Оповещено  : {meta['notified_family_members']} родственников")
    print(f"Ответ      : {meta['response_text']!r}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--user", default="voicetester")
    ap.add_argument("--password", default="voicetester123")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--wav", help="готовый WAV вместо микрофона (16 kHz mono PCM16)")
    ap.add_argument("--source", default="cli")
    args = ap.parse_args()

    print(f"[auth] {args.server} → {args.user}")
    token = auth(args.server, args.user, args.password)
    print("[auth] OK")

    if args.wav:
        wav_bytes = Path(args.wav).read_bytes()
        print(f"[wav] Из файла: {args.wav} ({len(wav_bytes)} байт)")
    else:
        wav_bytes = record_from_mic(args.duration)

    print(f"[http] POST {args.server}/api/v1/voice/converse ...")
    r = requests.post(
        f"{args.server}/api/v1/voice/converse",
        headers={"Authorization": f"Bearer {token}"},
        params={"source": args.source},
        files={"audio": ("input.wav", wav_bytes, "audio/wav")},
        timeout=180,
    )
    if r.status_code != 200:
        print(f"[http] FAIL {r.status_code}: {r.text}")
        return 1

    meta_b64 = r.headers.get("X-Pipeline-Metadata", "")
    if meta_b64:
        try:
            meta = json.loads(base64.b64decode(meta_b64).decode("utf-8"))
            pretty_meta(meta)
        except Exception as e:
            print(f"[meta] Не распарсил X-Pipeline-Metadata: {e}")

    play_wav(r.content)
    print("[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
