from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    email: EmailStr
    name: str
    surname: str


class UserCreate(UserBase):
    hashed_password: str


class UserUpdate(BaseModel):
    name: str | None = None
    surname: str | None = None


class UserOut(UserBase):
    id: int
    email_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class ChangePasswordRequest(BaseModel):
    user_id: int
    old_password: str
    new_password: str
