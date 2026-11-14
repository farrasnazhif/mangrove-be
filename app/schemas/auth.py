from pydantic import BaseModel

from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


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
