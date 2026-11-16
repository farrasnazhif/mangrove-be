from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode()) > 72:
            raise ValueError("Password exceeds bcrypt's 72 UTF-8 byte limit")
        return value


class UserResponse(BaseModel):
    id: str
    email: str
    role: UserRole  # server-derived, never from request body

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class CSRFTokenResponse(BaseModel):
    csrf_token: str


class MessageResponse(BaseModel):
    message: str
