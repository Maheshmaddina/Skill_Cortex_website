from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import Name, Password, Phone, UserOut


class RegisterRequest(BaseModel):
    name: Name
    email: EmailStr
    phone: Phone
    password: Password
    department_id: UUID


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: Password


class MessageResponse(BaseModel):
    message: str
