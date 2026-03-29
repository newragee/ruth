from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.health_stats import HealthStatsService
from app.services.visualization import VisualizationService
from app.services.reporting import ReportingService
from app.services.log_service import LogService

router = APIRouter()


@router.get("/")
async def get_stats(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    LogService(db).log_action(current_user.id, "view_stats")

    stats_service = HealthStatsService(db)
    viz_service = VisualizationService()
    report_service = ReportingService()

    metrics = stats_service.get_metrics(current_user.id, days=days)

    # Данные для таблицы
    table_data = []
    for m in metrics:
        row = {
            "id": m.id,
            "metric_type": m.metric_type,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }
        if m.metric_type == "blood_pressure":
            row["value"] = f"{m.value_json.get('systolic')}/{m.value_json.get('diastolic')}"
            row["unit"] = "мм рт.ст."
        elif m.metric_type == "pulse":
            row["value"] = str(m.value_json.get("value"))
            row["unit"] = "уд/мин"
        elif m.metric_type == "weight":
            row["value"] = str(m.value_json.get("value"))
            row["unit"] = "кг"
        elif m.metric_type == "temperature":
            row["value"] = str(m.value_json.get("value"))
            row["unit"] = "°C"
        elif m.metric_type == "blood_sugar":
            row["value"] = str(m.value_json.get("value"))
            row["unit"] = "ммоль/л"
        else:
            row["value"] = str(m.value_json)
            row["unit"] = ""
        table_data.append(row)

    # JSON-данные графиков (Plotly)
    charts = viz_service.generate_charts_json(current_user.id, db, days=days)

    # Рекомендации
    recommendation = report_service.generate_recommendation(current_user.id, db)

    return {
        "table": table_data,
        "charts": charts,
        "recommendation": recommendation,
        "days": days,
    }
