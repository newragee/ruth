from sqlalchemy.orm import Session
from app.services.health_stats import HealthStatsService
import numpy as np

class ReportingService:
    def generate_recommendation(self, user_id: int, db: Session) -> str:
        stats = HealthStatsService(db)
        metrics = stats.get_metrics(user_id, days=7)

        if not metrics:
            return "Нет данных за последнюю неделю. Вводите показатели регулярно для получения рекомендаций."

        # Простая логика: среднее давление и пульс
        bp_values = []
        pulse_values = []
        for m in metrics:
            if m.metric_type == "blood_pressure":
                bp_values.append((m.value_json.get("systolic"), m.value_json.get("diastolic")))
            elif m.metric_type == "pulse":
                pulse_values.append(m.value_json.get("value"))

        recs = []
        if bp_values:
            avg_sys = np.mean([v[0] for v in bp_values])
            avg_dia = np.mean([v[1] for v in bp_values])
            recs.append(f"Среднее давление за неделю: {avg_sys:.0f}/{avg_dia:.0f}.")
            if avg_sys > 140 or avg_dia > 90:
                recs.append("⚠️ Повышенное давление. Рекомендуется проконсультироваться с врачом.")
            elif avg_sys < 90 or avg_dia < 60:
                recs.append("⚠️ Пониженное давление. Обратите внимание на самочувствие.")
            else:
                recs.append("✅ Давление в норме.")

        if pulse_values:
            avg_pulse = np.mean(pulse_values)
            recs.append(f"Средний пульс: {avg_pulse:.0f} уд/мин.")
            if avg_pulse > 100:
                recs.append("⚠️ Пульс учащён (тахикардия).")
            elif avg_pulse < 60:
                recs.append("⚠️ Пульс замедлен (брадикардия).")
            else:
                recs.append("✅ Пульс в норме.")

        return "\n".join(recs) if recs else "Недостаточно данных для рекомендаций."
