from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    user_id: int | None = None
    user_name: str | None = None
    entity_type: str
    entity_id: int
    # Кого касается запись: для графика — сотрудник (у стертой учетки имя берется из самой записи).
    entity_name: str | None = None
    action: str
    center_id: int | None = None
    payload_json: dict | None = None
    created_at: datetime
