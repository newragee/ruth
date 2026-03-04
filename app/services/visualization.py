import plotly.graph_objects as go
import pandas as pd
from sqlalchemy.orm import Session
from app.services.health_stats import HealthStatsService

class VisualizationService:
    async def generate_chart(self, user_id: int, db: Session, metric_type: str = None) -> str:
        """
        Должен возвращать Plotly для показателей здоровья.
        Нихуя по итогу не возвращает
        потом разберусь, скорее всего ошибка фронтенда ебаного жс для долбоебов 
        """
        stats = HealthStatsService(db)
        metrics = stats.get_metrics(user_id, metric_type, days=30)
        if not metrics:
            return "<p>Нет данных для отображения графика.</p>"

        
        data = []
        for m in metrics:
            row = {"timestamp": m.timestamp, "metric_type": m.metric_type}
            
            if m.metric_type == "blood_pressure":
                row["systolic"] = m.value_json.get("systolic")
                row["diastolic"] = m.value_json.get("diastolic")
            else:
                # Для других показателей предполагаем ключ "value"
                row["value"] = m.value_json.get("value")
            data.append(row)
        df = pd.DataFrame(data)

        fig = go.Figure()
        if metric_type == "blood_pressure":
            # Отдельные линии для систолического и диастолического
            df_sorted = df.sort_values("timestamp")
            fig.add_trace(go.Scatter(x=df_sorted["timestamp"], y=df_sorted["systolic"],
                                     mode='lines+markers', name='Систолическое'))
            fig.add_trace(go.Scatter(x=df_sorted["timestamp"], y=df_sorted["diastolic"],
                                     mode='lines+markers', name='Диастолическое'))
            fig.update_layout(title="Динамика артериального давления",
                              xaxis_title="Дата", yaxis_title="Давление (мм рт.ст.)")
        else:
            # Общий график для других показателей
            df_sorted = df.sort_values("timestamp")
            fig.add_trace(go.Scatter(x=df_sorted["timestamp"], y=df_sorted["value"],
                                     mode='lines+markers', name=metric_type))
            fig.update_layout(title=f"Динамика {metric_type}",
                              xaxis_title="Дата", yaxis_title="Значение")

        # Возвращаем HTML-код графика
        # На самом деле нихуя мы тут не возвращаем у нас руки кривые 
        return fig.to_html(include_plotlyjs="cdn", div_id="chart")
