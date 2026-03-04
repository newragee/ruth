from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.health_stats import HealthStatsService
from app.services.visualization import VisualizationService
from app.services.reporting import ReportingService
from app.services.log_service import LogService

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def get_stats_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    
    LogService(db).log_action(current_user.id, "view_stats")

    stats_service = HealthStatsService(db)
    viz_service = VisualizationService()
    report_service = ReportingService()

    # все метрики за последние 30 дней
    metrics = stats_service.get_metrics(current_user.id, days=30)
    #ЭТО ПОКА ЧТО НЕ РАБОТАЕТ
    # графики для каждого типа метрик (упрощённо – один общий)
    chart_html = await viz_service.generate_chart(current_user.id, db)
    recommendation = report_service.generate_recommendation(current_user.id, db)


    html_content = f"""
    <html>
        <head><title>Статистика здоровья</title></head>
        <body>
            <h1>Статистика здоровья</h1>
            <div>{chart_html}</div>
            <h2>Рекомендации</h2>
            <pre>{recommendation}</pre>
            <p><a href="/">На главную</a></p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)
