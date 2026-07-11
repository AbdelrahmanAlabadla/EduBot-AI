from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional


class SetupSchema(BaseModel):
    school_name: str
    school_slug: str
    admin_name: str
    admin_email: EmailStr
    admin_password: str


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    school_id: UUID
    role: str


class StaffCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    school_id: UUID
    name: str
    email: str
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
