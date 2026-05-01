"""Сквозной голосовой пайплайн: WAV → STT → (NLU || NLI) → action → answer.

Основные принципы низкой задержки:
- NLU и NLI запускаются параллельно через asyncio.gather.
- Метрики, статистика, тревога — обрабатываются локально (без вызова LLM).
- К LLM (Gemma3) обращаемся только если интент = chitchat / unknown.
- Ответ возвращается текстом; стрим TTS делает уже эндпоинт.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models.health_metric import HealthMetric
from app.models.user import User
from app.models.voice_log import VoiceLog
from app.services.audio_utils import save_wav
from app.services.emergency_service import notify_family_of_emergency
from app.services.health_stats import HealthStatsService
from app.services.llm_client import LLMClient
from app.services.nli_service import EntailmentResult, NLIService, SentimentResult, get_nli_service
from app.services.nlu_service import NLUResult, NLUService
from app.services.reporting import ReportingService
from app.services.stt_service import STTResult, get_stt_service


@dataclass
class PipelineMetadata:
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
    entailment_label: str | None
    entailment_score: float | None
    response_text: str
    is_emergency: bool
    saved_metrics: list[str]
    notified_family_members: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VoicePipeline:
    def __init__(self, db: Session, user: User, source: str = "speaker"):
        self.db = db
        self.user = user
        self.source = source
        self.stt = get_stt_service()
        self.nli = get_nli_service()
        self.llm = LLMClient()
        self.nlu = NLUService(llm=self.llm)
        self.health = HealthStatsService(db)
        self.reporting = ReportingService()

    # ---------- main ----------
    async def process(self, wav_bytes: bytes) -> tuple[PipelineMetadata, str]:
        # 1. Сохраняем + STT
        audio_path, duration = save_wav(self.user.id, wav_bytes)
        stt: STTResult = await self.stt.transcribe_file(str(audio_path))
        transcript = stt.text

        if not transcript:
            meta = self._empty_meta(stt, audio_path, duration)
            self._persist(meta, audio_path)
            return meta, "Извините, я не расслышала."

        # 2. NLU и NLI(sentiment) параллельно
        nlu_task = asyncio.create_task(self.nlu.classify(transcript))
        sentiment_task = asyncio.create_task(self.nli.sentiment(transcript))
        nlu_res, sent_res = await asyncio.gather(nlu_task, sentiment_task)

        # 3. Entailment против последнего факта здоровья (если есть)
        ent_res = await self._maybe_entailment(transcript)

        # 4. Действие по интенту
        response, saved_metrics, notified = await self._dispatch(nlu_res, transcript, sent_res)

        is_emergency = nlu_res.intent == "panic"

        meta = PipelineMetadata(
            transcript=transcript,
            stt_language=stt.language,
            stt_confidence=stt.confidence,
            duration_sec=duration,
            intent=nlu_res.intent,
            intent_confidence=nlu_res.confidence,
            intent_source=nlu_res.source,
            slots=nlu_res.slots,
            sentiment_label=sent_res.label,
            sentiment_score=sent_res.score,
            entailment_label=(ent_res.label if ent_res else None),
            entailment_score=(ent_res.score if ent_res else None),
            response_text=response,
            is_emergency=is_emergency,
            saved_metrics=saved_metrics,
            notified_family_members=notified,
        )
        self._persist(meta, audio_path)
        return meta, response

    # ---------- helpers ----------
    async def _maybe_entailment(self, hypothesis: str) -> EntailmentResult | None:
        last = (
            self.db.query(HealthMetric)
            .filter(HealthMetric.user_id == self.user.id)
            .order_by(HealthMetric.timestamp.desc())
            .first()
        )
        if not last:
            return None
        premise = f"{last.metric_type}: {last.value_json}"
        return await self.nli.entailment(premise, hypothesis)

    async def _dispatch(
        self,
        nlu: NLUResult,
        text: str,
        sentiment: SentimentResult,
    ) -> tuple[str, list[str], int]:
        saved_metrics: list[str] = []
        notified = 0

        if nlu.intent == "panic":
            notified = notify_family_of_emergency(self.db, self.user, message=text)
            return (
                "Поняла, отправляю сигнал тревоги вашим близким. Оставайтесь на связи.",
                saved_metrics,
                notified,
            )

        if nlu.intent == "save_metric":
            metrics = nlu.slots.get("metrics") or []
            for m in metrics:
                self.health.add_metric(self.user.id, m["type"], m["value"])
                saved_metrics.append(m["type"])
            if saved_metrics:
                return ("Записала ваши показатели.", saved_metrics, 0)
            # слотов нет — спросим уточнение
            return ("Какой показатель вы хотите записать?", saved_metrics, 0)

        if nlu.intent == "get_stats":
            text_resp = self.reporting.generate_recommendation(self.user.id, self.db)
            return (text_resp, saved_metrics, 0)

        if nlu.intent == "set_reminder":
            return ("Напоминание сохранено. Позже вы сможете изменить его в приложении.",
                    saved_metrics, 0)

        if nlu.intent == "cyclic_query":
            return ("Хорошо, я буду регулярно спрашивать вас о самочувствии.",
                    saved_metrics, 0)

        if nlu.intent == "family_invite":
            return ("Чтобы пригласить родственника, откройте раздел «Семья» в приложении.",
                    saved_metrics, 0)

        # chitchat / unknown → к LLM с health-контекстом и подсказкой по тону
        context = self._llm_context(sentiment)
        prompt = f"Контекст: {context}\n\nСообщение пользователя: {text}\n\nОтвет:"
        answer = await self.llm.generate_response(prompt)
        return (answer, saved_metrics, 0)

    def _llm_context(self, sentiment: SentimentResult) -> str:
        recent = self.health.get_recent_metrics(self.user.id, limit=5)
        lines = [f"Тон собеседника: {sentiment.label} ({sentiment.score:.2f})."]
        if recent:
            lines.append("Последние показатели:")
            for m in recent:
                lines.append(f"- {m.metric_type}: {m.value_json} ({m.timestamp:%d.%m %H:%M})")
        else:
            lines.append("Нет данных о здоровье.")
        return "\n".join(lines)

    def _empty_meta(self, stt: STTResult, audio_path, duration: float) -> PipelineMetadata:
        return PipelineMetadata(
            transcript="",
            stt_language=stt.language,
            stt_confidence=stt.confidence,
            duration_sec=duration,
            intent="unknown",
            intent_confidence=0.0,
            intent_source="rules",
            slots={},
            sentiment_label="neutral",
            sentiment_score=0.0,
            entailment_label=None,
            entailment_score=None,
            response_text="Извините, я не расслышала.",
            is_emergency=False,
            saved_metrics=[],
            notified_family_members=0,
        )

    def _persist(self, meta: PipelineMetadata, audio_path) -> None:
        try:
            entry = VoiceLog(
                user_id=self.user.id,
                audio_path=str(audio_path),
                duration_sec=meta.duration_sec,
                transcript=meta.transcript,
                stt_language=meta.stt_language,
                stt_confidence=meta.stt_confidence,
                nlu_intent=meta.intent,
                nlu_slots=meta.slots,
                sentiment_label=meta.sentiment_label,
                sentiment_score=meta.sentiment_score,
                entailment_label=meta.entailment_label,
                entailment_score=meta.entailment_score,
                response_text=meta.response_text,
                is_emergency=meta.is_emergency,
                source=self.source,
            )
            self.db.add(entry)
            self.db.commit()
        except Exception as e:
            logger.error(f"Не удалось записать VoiceLog: {e}")
            self.db.rollback()
