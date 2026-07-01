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
    completed_doctor_role_ids: list[str] = Field(default_factory=list)
    suppressed_doctor_role_ids: list[str] = Field(default_factory=list)
