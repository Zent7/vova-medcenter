import json

from pydantic import BaseModel, Field, model_validator

from app.schemas.user_admin import StaffCenterRead


class LoginRequest(BaseModel):
    login: str
    password: str

    @model_validator(mode="before")
    @classmethod
    def unwrap_json_string(cls, value):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return value
            return parsed
        return value


class LoginResponse(BaseModel):
    user_id: int
    access_token: str
    token_type: str = "bearer"
    user_name: str
    role_code: str
    role_name: str
    # Основной медцентр сотрудника, с него он начинает работу. У админа его нет:
    # он видит все центры.
    center_id: int | None = None
    center_name: str | None = None
    all_centers: bool = False
    # Все центры, где сотрудник может работать, основной первым; у админа пусто.
    centers: list[StaffCenterRead] = Field(default_factory=list)


class LogoutAllResponse(BaseModel):
    ended_sessions: int
