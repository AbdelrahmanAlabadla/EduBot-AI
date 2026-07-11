from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class SchoolCreate(BaseModel):
    name: str
    slug: str
    logo_url: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = "active"


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = None


class SchoolResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str]
    website: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    language: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
