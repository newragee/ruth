import re
from app.services.llm_client import LLMClient
from app.services.health_stats import HealthStatsService
from app.services.visualization import VisualizationService
from app.services.reporting import ReportingService
from app.services.log_service import LogService
from sqlalchemy.orm import Session

class ChatProcessor:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.llm = LLMClient()
        self.health_stats = HealthStatsService(db)
        self.visualization = VisualizationService()
        self.reporting = ReportingService()
        self.logger = LogService(db)

    async def process_message(self, message: str) -> tuple[str, list[str] | None]:
        self.logger.log_action(self.user_id, "chat_message", f"Message: {message}")

        extracted = self._extract_health_metrics(message)
        saved_metrics = []
        if extracted:
            for metric in extracted:
                self.health_stats.add_metric(self.user_id, metric["type"], metric["value"])
                saved_metrics.append(metric["type"])
            self.logger.log_action(self.user_id, "metrics_saved", f"Saved: {saved_metrics}")

        if "статистика" in message.lower() or "график" in message.lower():
            recommendation = self.reporting.generate_recommendation(self.user_id, self.db)
            response = recommendation
            return response, saved_metrics if saved_metrics else None

        # Отправляем в LLM с контекстом здоровья
        context = self._build_context()
        prompt = f"Контекст: {context}\n\nСообщение пользователя: {message}\n\nОтвет:"
        llm_response = await self.llm.generate_response(prompt)

        from app.models.conversation import Conversation
        conv = Conversation(user_id=self.user_id, message=message, response=llm_response)
        self.db.add(conv)
        self.db.commit()

        return llm_response, saved_metrics if saved_metrics else None

    def _extract_health_metrics(self, text: str) -> list[dict]:
        extracted = []
        text_lower = text.lower()

        # Давление: обязательно ключевое слово ИЛИ формат X/Y в контексте здоровья
        bp_pattern = r"(?:давлени[ея]|ад)\s*[:=]?\s*(\d{2,3})\s*[/на]\s*(\d{2,3})"
        bp_match = re.search(bp_pattern, text_lower)
        if bp_match:
            sys_val = int(bp_match.group(1))
            dia_val = int(bp_match.group(2))
            if 60 <= sys_val <= 250 and 30 <= dia_val <= 150:
                extracted.append({
                    "type": "blood_pressure",
                    "value": {"systolic": sys_val, "diastolic": dia_val}
                })

        # Пульс: обязательно ключевое слово
        pulse_pattern = r"(?:пульс|чсс|сердцебиени[ея])\s*[:=]?\s*(\d{2,3})(?:\s*уд(?:ар(?:ов|а)?)?(?:\s*в?\s*мин(?:уту)?)?)?"
        pulse_match = re.search(pulse_pattern, text_lower)
        if pulse_match:
            val = int(pulse_match.group(1))
            if 30 <= val <= 220:
                extracted.append({
                    "type": "pulse",
                    "value": {"value": val}
                })

        # Вес: обязательно ключевое слово
        weight_pattern = r"(?:вес|масс[аы](?:\s*тела)?)\s*[:=]?\s*(\d{2,3}(?:[.,]\d{1,2})?)(?:\s*кг)?"
        weight_match = re.search(weight_pattern, text_lower)
        if weight_match:
            val = float(weight_match.group(1).replace(",", "."))
            if 20 <= val <= 300:
                extracted.append({
                    "type": "weight",
                    "value": {"value": val}
                })

        # Температура
        temp_pattern = r"(?:температур[аы]|темп)\s*[:=]?\s*(\d{2}(?:[.,]\d{1,2})?)(?:\s*°?[cсCС]?)?"
        temp_match = re.search(temp_pattern, text_lower)
        if temp_match:
            val = float(temp_match.group(1).replace(",", "."))
            if 34.0 <= val <= 42.0:
                extracted.append({
                    "type": "temperature",
                    "value": {"value": val}
                })

        # Сахар в крови
        sugar_pattern = r"(?:сахар|глюкоз[аы]|гликеми[яю])\s*[:=]?\s*(\d{1,2}(?:[.,]\d{1,2})?)(?:\s*ммоль)?"
        sugar_match = re.search(sugar_pattern, text_lower)
        if sugar_match:
            val = float(sugar_match.group(1).replace(",", "."))
            if 1.0 <= val <= 30.0:
                extracted.append({
                    "type": "blood_sugar",
                    "value": {"value": val}
                })

        return extracted

    def _build_context(self) -> str:
        recent = self.health_stats.get_recent_metrics(self.user_id, limit=5)
        if not recent:
            return "Нет данных о здоровье."
        lines = ["Последние показатели:"]
        for m in recent:
            lines.append(f"{m.metric_type}: {m.value_json} ({m.timestamp.strftime('%d.%m %H:%M')})")
        return "\n".join(lines)
