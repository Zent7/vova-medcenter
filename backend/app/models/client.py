from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    legacy_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    patient_number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    last_name: Mapped[str] = mapped_column(String(120), index=True)
    first_name: Mapped[str] = mapped_column(String(120), index=True)
    middle_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    birth_date: Mapped[date] = mapped_column(Date, index=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    citizenship: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arrival_country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    document_series: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    document_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    document_issued_by: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    snils: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    oms_policy: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    admission_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    doctor_gynecologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_stomatologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_dermatologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_neurologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_surgeon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_otolaryngologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_ophthalmologist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_therapist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_psychiatrist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_infectionist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_phthisiatrician: Mapped[str | None] = mapped_column(String(80), nullable=True)
    doctor_uzist: Mapped[str | None] = mapped_column(String(80), nullable=True)
    indications: Mapped[str | None] = mapped_column(Text, nullable=True)
    encounter_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    journal_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    no_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    flg: Mapped[str | None] = mapped_column(String(80), nullable=True)
    profession: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    work_place: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mkb10: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    real_date_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    legacy_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped["User | None"] = relationship("User")


Index("ix_clients_full_name_birth", Client.last_name, Client.first_name, Client.middle_name, Client.birth_date)
Index("ix_clients_document_identity", Client.document_series, Client.document_number)
