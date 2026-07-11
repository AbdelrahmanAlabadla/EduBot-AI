from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class AdmissionSettingsResponse(BaseModel):
    id: UUID
    school_id: UUID
    collect_student_name: bool
    collect_parent_name: bool
    collect_email: bool
    collect_phone: bool
    collect_student_grade: bool
    collect_interested_program: bool
    collect_visit_request: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdmissionSettingsUpdate(BaseModel):
    collect_student_name: Optional[bool] = None
    collect_parent_name: Optional[bool] = None
    collect_email: Optional[bool] = None
    collect_phone: Optional[bool] = None
    collect_student_grade: Optional[bool] = None
    collect_interested_program: Optional[bool] = None
    collect_visit_request: Optional[bool] = None
