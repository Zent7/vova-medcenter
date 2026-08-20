from datetime import datetime

from pydantic import BaseModel


class GeneratedDocumentRead(BaseModel):
    id: int
    encounter_id: int | None = None
    client_id: int
    template_id: int
    document_number: str | None = None
    series: str | None = None
    blank_form_id: int | None = None
    blank_number_snapshot: str | None = None
    file_name: str
    file_path: str
    generated_by_user_id: int | None = None
    generated_at: datetime
    file_deleted_at: datetime | None = None
    file_delete_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancelled_reason: str | None = None

    model_config = {"from_attributes": True}
