from pydantic import BaseModel
from datetime import datetime
from typing import Any

class HealthMetricCreate(BaseModel):
    metric_type: str
    value_json: dict[str, Any]

class HealthMetricResponse(BaseModel):
    id: int
    user_id: int
    metric_type: str
    value_json: dict
    timestamp: datetime

    class Config:
        from_attributes = True
