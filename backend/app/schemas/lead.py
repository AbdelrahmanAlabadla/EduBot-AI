from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class LeadResponse(BaseModel):
    id: UUID
    school_id: UUID
    conversation_id: Optional[UUID]
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    student_grade: Optional[str]
    interested_program: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadStatusUpdate(BaseModel):
    status: str
