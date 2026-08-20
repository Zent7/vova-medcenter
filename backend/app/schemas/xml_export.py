from pydantic import BaseModel


class XmlExportDayRead(BaseModel):
    date: str
    total_count: int
    available_count: int
    deleted_count: int


class XmlExportDeleteResponse(BaseModel):
    deleted_count: int
    missing_count: int = 0
    message: str


class XmlExportCleanupResponse(XmlExportDeleteResponse):
    retention_days: int
