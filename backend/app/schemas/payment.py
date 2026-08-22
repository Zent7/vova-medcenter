from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PaymentRead(BaseModel):
    id: int
    encounter_id: int
    payment_date: date
    payment_type: str
    amount: Decimal
    status: str
    comment: str | None = None

    model_config = {"from_attributes": True}


class CashReportServiceRead(BaseModel):
    service_id: int
    name: str
    quantity: int
    base_price: Decimal
    paid_price: Decimal
    discount: Decimal
    comment: str | None = None


class CashReportRowRead(BaseModel):
    payment_id: int
    encounter_id: int
    client_id: int
    patient_number: int
    client_full_name: str
    encounter_date: date
    encounter_created_at: datetime | None = None
    payment_date: date
    payment_type: str
    amount: Decimal
    discount: Decimal
    comment: str | None = None
    center_id: int
    center_name: str
    services: list[CashReportServiceRead] = Field(default_factory=list)
