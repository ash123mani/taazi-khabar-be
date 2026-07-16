from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserRegisterRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    email: str
    name: str | None = None
    google_id: str
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str | None
    is_admin: bool
    avatar_url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
