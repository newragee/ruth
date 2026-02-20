from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.core.database import Base

class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    metric_type = Column(String, nullable=False)  # например "blood_pressure", "pulse", "weight"
    value_json = Column(JSON, nullable=False)      # например {"systolic": 120, "diastolic": 80}
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
