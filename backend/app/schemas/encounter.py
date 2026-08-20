from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.encounter_service import EncounterServiceRead
from app.schemas.payment import PaymentRead


class EncounterBase(BaseModel):
    center_id: int
    client_id: int
    visit_type_id: int | None = None
    encounter_date: date
    payment_type: str
    total_amount: Decimal = Decimal("0.00")
    final_result: str | None = None
    comment: str | None = None
    suppressed_doctor_role_ids: list[str] = Field(default_factory=list)


class EncounterCreate(EncounterBase):
    pass


class EncounterUpdate(BaseModel):
    visit_type_id: int | None = None
    encounter_date: date | None = None
    payment_type: str | None = None
    total_amount: Decimal | None = None
    final_result: str | None = None
    comment: str | None = None
    suppressed_doctor_role_ids: list[str] | None = None
    status: str | None = None


class EncounterRead(EncounterBase):
    id: int
    status: str

    model_config = {"from_attributes": True}


class DeletedEncounterRead(BaseModel):
    id: int
    center_id: int
    client_id: int
    encounter_date: date
    payment_type: str
    total_amount: Decimal
    status: str
    deleted_at: datetime


class EncounterByServiceItemCreate(BaseModel):
    service_id: int
    unit_price: Decimal | None = Field(default=None, ge=0)
    payment_type: str = Field(default="cash", min_length=1)
    comment: str | None = None
    sequence_number: str | None = None
    notes: str | None = None


class EncountersByServicesCreate(BaseModel):
    center_id: int
    client_id: int
    encounter_date: date
    visit_type_id: int | None = None
    services: list[EncounterByServiceItemCreate] = Field(min_length=1)


class EncounterByServiceRead(BaseModel):
    encounter: EncounterRead
    service: EncounterServiceRead
    payment: PaymentRead
