import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database.base import Base


class AdmissionSetting(Base):
    __tablename__ = "admission_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), unique=True, nullable=False)
    collect_student_name = Column(Boolean, default=False)
    collect_parent_name = Column(Boolean, default=False)
    collect_email = Column(Boolean, default=False)
    collect_phone = Column(Boolean, default=False)
    collect_student_grade = Column(Boolean, default=False)
    collect_interested_program = Column(Boolean, default=False)
    collect_visit_request = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
