from pydantic import BaseModel


class ClientImportExcelRequest(BaseModel):
    file_name: str
    file_content_base64: str


class ClientImportPreviewRow(BaseModel):
    row_number: int
    patient_number: int | None = None
    full_name: str
    birth_date: str | None = None
    organization: str | None = None
    service_name: str | None = None
    encounter_date: str | None = None
    status: str
    match_reason: str | None = None


class ClientImportPreviewResponse(BaseModel):
    file_name: str
    parsed_rows: int
    created_candidates: int
    update_candidates: int
    service_rows: int
    service_warnings: list[str] = []
    service_warning_rows: int = 0
    preview_rows: list[ClientImportPreviewRow]


class ClientImportResultResponse(BaseModel):
    file_name: str
    parsed_rows: int
    created: int
    updated: int
    encounters_created: int
    service_warnings: list[str] = []
    service_warning_rows: int = 0
