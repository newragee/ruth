import plotly.graph_objects as go
import json
from sqlalchemy.orm import Session
from app.services.health_stats import HealthStatsService

METRIC_LABELS = {
    "blood_pressure": "Артериальное давление",
    "pulse": "Пульс (уд/мин)",
    "weight": "Вес (кг)",
    "temperature": "Температура (°C)",
    "blood_sugar": "Сахар в крови (ммоль/л)",
}


class VisualizationService:
    def generate_charts_json(self, user_id: int, db: Session, days: int = 30) -> dict[str, dict]:
        """Возвращает словарь {metric_type: plotly_json} для рендеринга на клиенте."""
        stats = HealthStatsService(db)
        metrics = stats.get_metrics(user_id, days=days)
        if not metrics:
            return {}

        grouped: dict[str, list] = {}
        for m in metrics:
            grouped.setdefault(m.metric_type, []).append(m)

        charts = {}
        for metric_type, items in grouped.items():
            charts[metric_type] = self._build_chart_json(metric_type, items)
        return charts

    def _build_chart_json(self, metric_type: str, items: list) -> dict:
        label = METRIC_LABELS.get(metric_type, metric_type)
        fig = go.Figure()

        timestamps = [m.timestamp.isoformat() for m in items]

        if metric_type == "blood_pressure":
            systolic = [m.value_json.get("systolic") for m in items]
            diastolic = [m.value_json.get("diastolic") for m in items]
            fig.add_trace(go.Scatter(
                x=timestamps, y=systolic,
                mode="lines+markers", name="Систолическое",
                line=dict(color="#e74c3c")
            ))
            fig.add_trace(go.Scatter(
                x=timestamps, y=diastolic,
                mode="lines+markers", name="Диастолическое",
                line=dict(color="#3498db")
            ))
            fig.update_layout(yaxis_title="мм рт.ст.")
        else:
            values = [m.value_json.get("value") for m in items]
            fig.add_trace(go.Scatter(
                x=timestamps, y=values,
                mode="lines+markers", name=label,
                line=dict(color="#2ecc71")
            ))
            fig.update_layout(yaxis_title=label)

        fig.update_layout(
            title=label,
            xaxis_title="Дата",
            template="plotly_white",
            height=350,
            margin=dict(l=50, r=30, t=50, b=40),
        )

        return json.loads(fig.to_json())

    async def generate_chart(self, user_id: int, db: Session, metric_type: str = None) -> str:
        """Обратная совместимость для chat_processor (текстовый fallback)."""
        stats = HealthStatsService(db)
        metrics = stats.get_metrics(user_id, days=30)
        if not metrics:
            return "Нет данных для отображения графика."
        summary = []
        for m in metrics:
            if m.metric_type == "blood_pressure":
                summary.append(f"{m.timestamp.strftime('%d.%m %H:%M')}: {m.value_json.get('systolic')}/{m.value_json.get('diastolic')} мм рт.ст.")
            else:
                summary.append(f"{m.timestamp.strftime('%d.%m %H:%M')}: {m.metric_type} = {m.value_json.get('value')}")
        return "Данные за последние 30 дней:\n" + "\n".join(summary)
