from sqlalchemy.orm import Session
from app.models.health_metric import HealthMetric
from app.schemas.health import HealthMetricCreate
from datetime import datetime, timedelta

class HealthStatsService:
    def __init__(self, db: Session):
        self.db = db

    def add_metric(self, user_id: int, metric_type: str, value_json: dict) -> HealthMetric:
        metric = HealthMetric(
            user_id=user_id,
            metric_type=metric_type,
            value_json=value_json
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_metrics(self, user_id: int, metric_type: str = None, days: int = 30):
        query = self.db.query(HealthMetric).filter(HealthMetric.user_id == user_id)
        if metric_type:
            query = query.filter(HealthMetric.metric_type == metric_type)
        if days:
            since = datetime.now() - timedelta(days=days)
            query = query.filter(HealthMetric.timestamp >= since)
        return query.order_by(HealthMetric.timestamp).all()

    def get_recent_metrics(self, user_id: int, limit: int = 5):
        return self.db.query(HealthMetric).filter(HealthMetric.user_id == user_id)\
            .order_by(HealthMetric.timestamp.desc()).limit(limit).all()
