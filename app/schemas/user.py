from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr
    name: str
    surname: str


class UserCreate(UserBase):
    hashed_password: str


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    name: str | None = None
    surname: str | None = None


class UserOut(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
