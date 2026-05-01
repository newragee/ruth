"""NLI: два независимых компонента.

1. Sentiment  — `seara/rubert-tiny2-russian-sentiment` (метки neutral/positive/negative).
   Используется для отметки эмоционального тона реплик; помогает выявлять
   признаки ухудшения состояния даже когда явной тревожной фразы нет.

2. Entailment — `cointegrated/rubert-base-cased-nli-threeway`
   (entailment / contradiction / neutral). Берём в роли premise последний
   сохранённый факт о здоровье (или предыдущую реплику пользователя),
   в роли hypothesis — текущее сообщение. Так детектим противоречия:
   например, premise «давление 160/100», hypothesis «у меня давление в норме»
   → contradiction → можно переспросить пользователя.

Модели грузятся лениво (singleton), чтобы старт сервера не зависел от
наличия инференс-моделей; первый запрос будет дольше последующих.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from loguru import logger

from app.core.config import settings


@dataclass
class SentimentResult:
    label: str           # 'positive' | 'neutral' | 'negative'
    score: float


@dataclass
class EntailmentResult:
    label: str           # 'entailment' | 'neutral' | 'contradiction'
    score: float


class _LazyPipeline:
    def __init__(self, task: str, model: str):
        self._task = task
        self._model = model
        self._pipe = None
        self._lock = Lock()

    def get(self):
        if self._pipe is None:
            with self._lock:
                if self._pipe is None:
                    from transformers import pipeline
                    logger.info(f"Загрузка HF pipeline: task={self._task} model={self._model}")
                    self._pipe = pipeline(self._task, model=self._model, device=-1)
        return self._pipe


class NLIService:
    _instance: Optional["NLIService"] = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_done = False
            return cls._instance

    def __init__(self):
        if self._init_done:
            return
        self._sentiment = _LazyPipeline("sentiment-analysis", settings.NLI_SENTIMENT_MODEL)
        self._entailment = _LazyPipeline("text-classification", settings.NLI_ENTAILMENT_MODEL)
        self._init_done = True

    # ----- sentiment -----
    def _sentiment_sync(self, text: str) -> SentimentResult:
        try:
            res = self._sentiment.get()(text, truncation=True)[0]
            return SentimentResult(label=str(res["label"]).lower(), score=float(res["score"]))
        except Exception as e:
            logger.warning(f"Sentiment упал: {e}")
            return SentimentResult(label="neutral", score=0.0)

    async def sentiment(self, text: str) -> SentimentResult:
        return await asyncio.to_thread(self._sentiment_sync, text)

    # ----- entailment -----
    def _entailment_sync(self, premise: str, hypothesis: str) -> EntailmentResult:
        try:
            pipe = self._entailment.get()
            # модель ждёт пару — передаём через text/text_pair
            out = pipe({"text": premise, "text_pair": hypothesis}, truncation=True)
            if isinstance(out, list):
                out = out[0]
            label = str(out["label"]).lower()
            # нормализуем имена меток к канону
            mapping = {
                "entailment": "entailment",
                "contradiction": "contradiction",
                "neutral": "neutral",
                "label_0": "entailment",
                "label_1": "neutral",
                "label_2": "contradiction",
            }
            return EntailmentResult(label=mapping.get(label, label), score=float(out["score"]))
        except Exception as e:
            logger.warning(f"Entailment упал: {e}")
            return EntailmentResult(label="neutral", score=0.0)

    async def entailment(self, premise: str, hypothesis: str) -> EntailmentResult:
        return await asyncio.to_thread(self._entailment_sync, premise, hypothesis)


def get_nli_service() -> NLIService:
    return NLIService()
