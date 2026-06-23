from datetime import date, datetime

from pydantic import BaseModel, Field


class ClientBase(BaseModel):
    last_name: str
    first_name: str
    middle_name: str | None = None
    birth_date: date
    sex: str | None = None
    phone: str | None = None
    email: str | None = None
    document_type: str | None = None
    document_series: str | None = None
    document_number: str | None = None
    document_issued_by: str | None = None
    document_issued_date: date | None = None
    snils: str | None = None
    oms_policy: str | None = None
    address_text: str | None = None
    notes: str | None = None
    registration_text: str | None = None
    admission_category: str | None = None
    reference_number: str | None = None
    doctor_gynecologist: str | None = None
    doctor_stomatologist: str | None = None
    doctor_dermatologist: str | None = None
    doctor_neurologist: str | None = None
    doctor_surgeon: str | None = None
    doctor_otolaryngologist: str | None = None
    doctor_ophthalmologist: str | None = None
    doctor_therapist: str | None = None
    doctor_psychiatrist: str | None = None
    doctor_infectionist: str | None = None
    doctor_phthisiatrician: str | None = None
    doctor_uzist: str | None = None
    indications: str | None = None
    encounter_date_text: str | None = None
    card_number: str | None = None
    journal_number: str | None = None
    no_number: str | None = None
    flg: str | None = None
    profession: str | None = None
    work_place: str | None = None
    organization: str | None = None
    mkb10: str | None = None
    real_date_text: str | None = None
    legacy_payload_json: dict | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(ClientBase):
    pass


class ClientRead(ClientBase):
    id: int
    patient_number: int
    created_at: datetime | None = None
    latest_encounter_created_at: datetime | None = None
    services: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ClientSearchRead(BaseModel):
    id: int
    patient_number: int
    created_at: datetime | None = None
    latest_encounter_created_at: datetime | None = None
    last_name: str
    first_name: str
    middle_name: str | None = None
    birth_date: date
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
    services: list[str] = Field(default_factory=list)


class DeletedClientRead(BaseModel):
    id: int
    patient_number: int
    full_name: str
    birth_date: date
    deleted_at: datetime
