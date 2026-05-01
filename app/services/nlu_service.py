"""NLU: определение интента + слотов.

Гибрид:
1. Быстрый путь — regex и ключевые слова. Срабатывает мгновенно
   на типовые фразы (метрики здоровья, тревога, статистика, напоминания).
2. Fallback — Gemma3 через Ollama в format=json. Используется, когда
   regex ничего не дал, либо confidence низкий.

Слоты для метрик переиспользуют логику из ChatProcessor._extract_health_metrics.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.services.llm_client import LLMClient


# Канонический набор интентов
INTENTS = (
    "save_metric",      # пользователь сообщил замер (давление/пульс/...)
    "get_stats",        # просит показать статистику/график
    "panic",            # тревога / SOS
    "set_reminder",     # «напомни...»
    "cyclic_query",     # настроить регулярные опросы
    "family_invite",    # пригласить в семью
    "chitchat",         # обычный диалог / вопрос помощнику
    "unknown",
)

_PANIC_TOKENS = (
    "помогите", "помоги", "плохо мне", "мне плохо", "тревога",
    "вызови скорую", "скорую", "беда", "сос", "сигнал тревоги",
    "не могу дышать", "сильная боль", "теряю сознание", "упал",
)

_STATS_TOKENS = ("статистик", "график", "историю", "покажи измерен", "динамик")

_REMINDER_TOKENS = ("напомни", "напоминай", "напоминание")

_CYCLIC_TOKENS = ("каждый день", "ежедневно", "каждое утро", "регулярно спрашивай",
                  "опрашивай меня", "спрашивай меня каждый")

_FAMILY_TOKENS = ("пригласи в семью", "добавь в семью", "семейный код", "код приглашен")


@dataclass
class NLUResult:
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = "rules"  # 'rules' | 'llm'


class NLUService:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    # --- regex слоты для метрик (та же логика, что в chat_processor) ---
    @staticmethod
    def extract_metrics(text: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        t = text.lower()

        m = re.search(r"(?:давлени[ея]|ад)\s*[:=]?\s*(\d{2,3})\s*[/на ]+\s*(\d{2,3})", t)
        if m:
            sys_, dia = int(m.group(1)), int(m.group(2))
            if 60 <= sys_ <= 250 and 30 <= dia <= 150:
                out.append({"type": "blood_pressure", "value": {"systolic": sys_, "diastolic": dia}})

        m = re.search(r"(?:пульс|чсс|сердцебиени[ея])\s*[:=]?\s*(\d{2,3})", t)
        if m:
            v = int(m.group(1))
            if 30 <= v <= 220:
                out.append({"type": "pulse", "value": {"value": v}})

        m = re.search(r"(?:вес|масс[аы](?:\s*тела)?)\s*[:=]?\s*(\d{2,3}(?:[.,]\d{1,2})?)", t)
        if m:
            v = float(m.group(1).replace(",", "."))
            if 20 <= v <= 300:
                out.append({"type": "weight", "value": {"value": v}})

        m = re.search(r"(?:температур[аы]|темп)\s*[:=]?\s*(\d{2}(?:[.,]\d{1,2})?)", t)
        if m:
            v = float(m.group(1).replace(",", "."))
            if 34.0 <= v <= 42.0:
                out.append({"type": "temperature", "value": {"value": v}})

        m = re.search(r"(?:сахар|глюкоз[аы]|гликеми[яю])\s*[:=]?\s*(\d{1,2}(?:[.,]\d{1,2})?)", t)
        if m:
            v = float(m.group(1).replace(",", "."))
            if 1.0 <= v <= 30.0:
                out.append({"type": "blood_sugar", "value": {"value": v}})

        return out

    def _rule_based(self, text: str) -> NLUResult | None:
        t = text.lower().strip()
        if not t:
            return NLUResult(intent="unknown", confidence=1.0, source="rules")

        # 1) Тревога — самый высокий приоритет
        if any(tok in t for tok in _PANIC_TOKENS):
            return NLUResult(intent="panic", slots={}, confidence=0.95, source="rules")

        # 2) Метрики
        metrics = self.extract_metrics(t)
        if metrics:
            return NLUResult(
                intent="save_metric",
                slots={"metrics": metrics},
                confidence=0.9,
                source="rules",
            )

        # 3) Статистика
        if any(tok in t for tok in _STATS_TOKENS):
            return NLUResult(intent="get_stats", slots={}, confidence=0.85, source="rules")

        # 4) Напоминание
        if any(tok in t for tok in _REMINDER_TOKENS):
            return NLUResult(intent="set_reminder", slots={"raw": text}, confidence=0.7, source="rules")

        # 5) Циклический опрос
        if any(tok in t for tok in _CYCLIC_TOKENS):
            return NLUResult(intent="cyclic_query", slots={"raw": text}, confidence=0.7, source="rules")

        # 6) Семья
        if any(tok in t for tok in _FAMILY_TOKENS):
            return NLUResult(intent="family_invite", slots={"raw": text}, confidence=0.7, source="rules")

        return None

    async def _llm_classify(self, text: str) -> NLUResult:
        system = (
            "Ты классификатор намерений русскоязычного голосового помощника по здоровью. "
            "Верни СТРОГО JSON: {\"intent\": <одно из: save_metric, get_stats, panic, "
            "set_reminder, cyclic_query, family_invite, chitchat, unknown>, "
            "\"slots\": {...}, \"confidence\": <0..1>}. "
            "Никакого текста вне JSON."
        )
        prompt = f"Сообщение пользователя: {text}\nJSON:"
        raw = await self.llm.generate_json(prompt, system=system)
        if not raw:
            return NLUResult(intent="chitchat", confidence=0.3, source="llm")
        try:
            data = json.loads(raw)
            intent = data.get("intent", "chitchat")
            if intent not in INTENTS:
                intent = "chitchat"
            return NLUResult(
                intent=intent,
                slots=data.get("slots") or {},
                confidence=float(data.get("confidence") or 0.5),
                source="llm",
            )
        except Exception as e:
            logger.warning(f"LLM NLU вернул не-JSON: {raw!r} ({e})")
            return NLUResult(intent="chitchat", confidence=0.3, source="llm")

    async def classify(self, text: str) -> NLUResult:
        rule = self._rule_based(text)
        if rule and rule.confidence >= 0.7:
            return rule
        return await self._llm_classify(text)
