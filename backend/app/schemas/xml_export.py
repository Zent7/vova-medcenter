from pydantic import BaseModel


class XmlExportDayRead(BaseModel):
    date: str
    total_count: int
    available_count: int
    deleted_count: int
    blank_count: int = 0


class XmlExportDeleteResponse(BaseModel):
    deleted_count: int
    missing_count: int = 0
    message: str


class XmlExportCleanupResponse(XmlExportDeleteResponse):
    retention_days: int


class XmlExportBuildSkip(BaseModel):
    client_name: str
    blank_number: str
    reason: str


class XmlExportBuildResponse(BaseModel):
    date: str
    generated_count: int
    replaced_count: int
    skipped: list[XmlExportBuildSkip]
    message: str
