from datetime import date, datetime

from pydantic import BaseModel, Field


class BlankTypeRead(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


class BlankSeriesRead(BaseModel):
    series: str | None = None
    free_count: int
    next_form_id: int | None = None
    next_full_number: str | None = None


class BlankBatchBase(BaseModel):
    center_id: int | None = None
    blank_type: str
    series: str | None = None
    number_from: int = Field(ge=0)
    number_to: int = Field(ge=0)
    number_width: int = Field(default=6, ge=1, le=20)
    received_at: date | None = None
    comment: str | None = None


class BlankBatchCreate(BlankBatchBase):
    pass


class BlankBatchRead(BlankBatchBase):
    id: int
    quantity: int
    created_by_user_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Дополнительная статистика по партии для UI.
    free_count: int = 0
    issued_count: int = 0
    spoiled_count: int = 0
    cancelled_count: int = 0

    model_config = {"from_attributes": True}


class BlankFormRead(BaseModel):
    id: int
    batch_id: int
    center_id: int | None = None
    blank_type: str
    series: str | None = None
    number_value: int
    full_number: str
    status: str
    client_id: int | None = None
    encounter_id: int | None = None
    client_document_id: int | None = None
    generated_document_id: int | None = None
    issued_at: datetime | None = None
    issued_by_user_id: int | None = None
    spoiled_at: datetime | None = None
    spoiled_by_user_id: int | None = None
    spoiled_reason: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancelled_reason: str | None = None

    # Подтянутые из связанных таблиц значения для удобства фронтенда.
    client_full_name: str | None = None
    document_label: str | None = None
    issued_by_name: str | None = None

    model_config = {"from_attributes": True}


class BlankFormSpoilRequest(BaseModel):
    reason: str | None = None


class BlankStatsItem(BaseModel):
    blank_type: str
    blank_type_name: str
    total: int
    free: int
    issued: int
    spoiled: int
    cancelled: int


class BlankStatsResponse(BaseModel):
    items: list[BlankStatsItem]
