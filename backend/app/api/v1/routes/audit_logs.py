from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.auth import require_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogRead

# Журнал аудита видит только админ: в нем ставки и правки графика сотрудников.
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditLogRead]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)

    logs = db.execute(query).scalars().all()
    user_ids = sorted({log.user_id for log in logs if log.user_id is not None})
    users_by_id: dict[int, User] = {}
    if user_ids:
        users = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        users_by_id = {user.id: user for user in users}

    return [
        AuditLogRead(
            id=log.id,
            user_id=log.user_id,
            user_name=users_by_id.get(log.user_id).full_name if log.user_id in users_by_id else None,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            center_id=log.center_id,
            payload_json=log.payload_json,
            created_at=log.created_at,
        )
        for log in logs
    ]
