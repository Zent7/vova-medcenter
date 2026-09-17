from decimal import Decimal

from pydantic import BaseModel


class ServiceRead(BaseModel):
    id: int
    legacy_source_id: int | None = None
    category_id: int | None = None
    code: str
    name: str
    price: Decimal
    is_active: bool
    requires_sequence: bool = False
    recall_after_days: int | None = None
    doctor_role_ids: list[int] = []

    model_config = {"from_attributes": True}


class ServiceCreate(BaseModel):
    category_id: int | None = None
    name: str
    price: Decimal = Decimal("0")
    is_active: bool = True
    requires_sequence: bool = False
    recall_after_days: int | None = None
    doctor_role_ids: list[int] = []


class ServiceUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = None
    price: Decimal | None = None
    is_active: bool | None = None
    requires_sequence: bool | None = None
    recall_after_days: int | None = None
    doctor_role_ids: list[int] | None = None
