"""Тревожная кнопка: рассылка уведомлений членам семьи пользователя."""
from __future__ import annotations

from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from app.models.family import FamilyMember
from app.models.log import Log
from app.models.user import User


def notify_family_of_emergency(db: Session, user: User, message: str | None = None) -> int:
    """Создаёт уведомления (через таблицу logs с action='emergency_notify')
    для всех членов семей, в которых состоит пользователь.

    Возвращает количество оповещённых членов семьи. Канал доставки
    (push / SMS / email) подключается отдельно — здесь персистится
    событие, на которое подпишется внешний notifier.
    """
    families = (
        db.query(FamilyMember.family_id)
        .filter(FamilyMember.user_id == user.id)
        .all()
    )
    family_ids = [f.family_id for f in families]
    if not family_ids:
        logger.warning(f"Emergency для user_id={user.id}, но семей нет")
        return 0

    targets = (
        db.query(FamilyMember)
        .filter(FamilyMember.family_id.in_(family_ids))
        .filter(FamilyMember.user_id != user.id)
        .all()
    )

    payload = (
        f"EMERGENCY user_id={user.id} username={user.username} "
        f"at={datetime.utcnow().isoformat()}Z message={message or ''!r}"
    )

    for tgt in targets:
        db.add(Log(user_id=tgt.user_id, action="emergency_notify", details=payload))
    db.add(Log(user_id=user.id, action="emergency_triggered", details=payload))
    db.commit()
    logger.info(f"Emergency: оповещено {len(targets)} родственников для user_id={user.id}")
    return len(targets)
