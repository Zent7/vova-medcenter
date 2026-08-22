from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    clients_count: int
    encounters_count: int
    services_count: int
    recalls_due_count: int


class DashboardClientDoctorStatusService(BaseModel):
    service_id: int
    notes: str | None = None


class DashboardClientDoctorStatus(BaseModel):
    client_id: int
    encounter_id: int | None = None
    encounter_status: str | None = None
    blank_number: str | None = None
    services: list[DashboardClientDoctorStatusService] = Field(default_factory=list)
    existing_doctor_role_ids: list[str] = Field(default_factory=list)
    completed_doctor_role_ids: list[str] = Field(default_factory=list)
    suppressed_doctor_role_ids: list[str] = Field(default_factory=list)
    has_glasses: bool = False


class DashboardEncounterRow(BaseModel):
    """A journal row backed by one encounter and one client.

    ``id`` intentionally remains the client id for compatibility with the
    existing dashboard client mapper.  ``encounter_id`` is the stable row
    identity when an encounter exists.
    """

    id: int
    client_id: int
    patient_number: int
    created_at: datetime | None = None
    last_name: str
    first_name: str
    middle_name: str | None = None
    birth_date: date
    sex: str | None = None
    phone: str | None = None
    document_type: str | None = None
    document_series: str | None = None
    document_number: str | None = None
    snils: str | None = None
    address_text: str | None = None
    registration_text: str | None = None
    admission_category: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    encounter_date_text: str | None = None
    card_number: str | None = None
    profession: str | None = None
    work_place: str | None = None
    organization: str | None = None
    real_date_text: str | None = None

    encounter_id: int | None = None
    encounter_date: date | None = None
    encounter_created_at: datetime | None = None
    latest_encounter_created_at: datetime | None = None
    encounter_status: str | None = None
    center_id: int | None = None
    center_name: str | None = None
    payment_type: str | None = None
    total_amount: Decimal | None = None
    comment: str | None = None
    services: list[str] = Field(default_factory=list)
