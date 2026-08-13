from pydantic import BaseModel


class DoctorRoleRead(BaseModel):
    id: int
    code: str
    name: str
    full_name: str | None = None
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class DoctorRoleUpdate(BaseModel):
    full_name: str | None = None
