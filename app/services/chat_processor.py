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
        # Логируем входящее сообщение
        self.logger.log_action(self.user_id, "chat_message", f"Message: {message}")

        # 1. Пытаемся извлечь показатели здоровья
        extracted = self._extract_health_metrics(message)
        saved_metrics = []
        if extracted:
            for metric in extracted:
                saved = self.health_stats.add_metric(self.user_id, metric["type"], metric["value"])
                saved_metrics.append(metric["type"])
            self.logger.log_action(self.user_id, "metrics_saved", f"Saved: {saved_metrics}")

        # 2. Определяем намерение (упрощённо)
        if "статистика" in message.lower() or "график" in message.lower() or "покажи" in message.lower():
            # Запрос статистики
            # Для простоты вернём сгенерированный график и рекомендацию
            # В реальности нужно анализировать период и тип показателя
            chart_html = await self.visualization.generate_chart(self.user_id, self.db)
            recommendation = self.reporting.generate_recommendation(self.user_id, self.db)
            response = f"{recommendation}\n\n{chart_html}"
            return response, saved_metrics

        # 3. Иначе отправляем в LLM
        # Можно добавить контекст (последние показатели) в промпт
        context = self._build_context()
        prompt = f"Контекст: {context}\n\nСообщение пользователя: {message}\n\nОтвет:"
        llm_response = await self.llm.generate_response(prompt)

        # Сохраняем диалог
        from app.models.conversation import Conversation
        conv = Conversation(user_id=self.user_id, message=message, response=llm_response)
        self.db.add(conv)
        self.db.commit()

        return llm_response, saved_metrics if saved_metrics else None

    def _extract_health_metrics(self, text: str) -> list[dict]:
        """Извлекает показатели из текста с помощью регулярных выражений."""
        extracted = []
        # Давление: "давление 120/80" или "120/80"
        bp_pattern = r"(?:давление\s*)?(\d{2,3})\/(\d{2,3})"
        bp_match = re.search(bp_pattern, text, re.IGNORECASE)
        if bp_match:
            extracted.append({
                "type": "blood_pressure",
                "value": {"systolic": int(bp_match.group(1)), "diastolic": int(bp_match.group(2))}
            })

        # Пульс: "пульс 75" или "75 ударов"
        pulse_pattern = r"(?:пульс\s*)?(\d{2,3})(?:\s*уд/?мин)?"
        pulse_match = re.search(pulse_pattern, text, re.IGNORECASE)
        if pulse_match:
            extracted.append({
                "type": "pulse",
                "value": {"value": int(pulse_match.group(1))}
            })

        # Вес: "вес 70" или "70 кг"
        weight_pattern = r"(?:вес\s*)?(\d{2,3})(?:\s*кг)?"
        weight_match = re.search(weight_pattern, text, re.IGNORECASE)
        if weight_match:
            extracted.append({
                "type": "weight",
                "value": {"value": int(weight_match.group(1))}
            })

        return extracted

    def _build_context(self) -> str:
        """Формирует контекст из последних показателей здоровья."""
        recent = self.health_stats.get_recent_metrics(self.user_id, limit=5)
        if not recent:
            return "Нет данных о здоровье."
        lines = ["Последние показатели:"]
        for m in recent:
            lines.append(f"{m.metric_type}: {m.value_json} (в {m.timestamp.strftime('%d.%m %H:%M')})")
        return "\n".join(lines)
