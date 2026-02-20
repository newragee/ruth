from sqlalchemy.orm import Session
from app.models.log import Log

class LogService:
    def __init__(self, db: Session):
        self.db = db

    def log_action(self, user_id: int | None, action: str, details: str = None):
        log = Log(user_id=user_id, action=action, details=details)
        self.db.add(log)
        self.db.commit()
