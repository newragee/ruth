#ТУТ НИЧИВО НЕ РАБОТАЕТ БЕБЕБЕ

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.log import Log
from app.services.log_service import LogService

router = APIRouter()

@router.get("/")
def get_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Простейшие уведомления 
    # Для демо заглушка
    LogService(db).log_action(current_user.id, "view_notifications")
    return {"notifications": ["У вас нет новых уведомлений"]}
