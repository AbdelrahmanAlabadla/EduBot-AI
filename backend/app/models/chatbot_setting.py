import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from app.database.base import Base


class ChatbotSetting(Base):
    __tablename__ = "chatbot_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), unique=True, nullable=False)
    chatbot_name = Column(String(255), nullable=True)
    welcome_message = Column(Text, nullable=True)
    default_language = Column(String(10), default="en")
    supported_languages = Column(JSON, default=lambda: ["en", "ar"])
    logo_url = Column(String(500), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    theme_color = Column(String(20), nullable=True)
    collect_contact_info = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
