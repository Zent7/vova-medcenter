import json

from pydantic import BaseModel, model_validator


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


class LogoutAllResponse(BaseModel):
    ended_sessions: int
