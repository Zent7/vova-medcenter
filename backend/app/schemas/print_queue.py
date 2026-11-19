from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.print_queue import MAX_COPIES


class PrintJobCreate(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    copies: int = Field(default=1, ge=1, le=MAX_COPIES)


class PrintJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    copies: int
    status: str
    error: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    finished_at: datetime | None = None


class AgentHeartbeatResponse(BaseModel):
    ok: bool = True
    agent_id: int
    name: str
    center_id: int | None = None
    printer_name: str | None = None
    server_time: datetime


class AgentJob(BaseModel):
    id: int
    file_name: str
    copies: int
    printer_name: str | None = None
    file_url: str


class AgentClaimResponse(BaseModel):
    job: AgentJob | None = None


class AgentResultRequest(BaseModel):
    ok: bool
    error: str | None = Field(default=None, max_length=500)
