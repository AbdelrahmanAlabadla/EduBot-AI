from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class ChatbotSettingsResponse(BaseModel):
    id: UUID
    school_id: UUID
    chatbot_name: Optional[str]
    welcome_message: Optional[str]
    default_language: str
    supported_languages: Optional[list]
    logo_url: Optional[str]
    avatar_url: Optional[str]
    theme_color: Optional[str]
    collect_contact_info: bool
    fallback_message_en: Optional[str]
    fallback_message_ar: Optional[str]
    verification_note_en: Optional[str]
    verification_note_ar: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatbotSettingsUpdate(BaseModel):
    chatbot_name: Optional[str] = None
    welcome_message: Optional[str] = None
    default_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    logo_url: Optional[str] = None
    avatar_url: Optional[str] = None
    theme_color: Optional[str] = None
    collect_contact_info: Optional[bool] = None
    fallback_message_en: Optional[str] = None
    fallback_message_ar: Optional[str] = None
    verification_note_en: Optional[str] = None
    verification_note_ar: Optional[str] = None


class WidgetResponse(BaseModel):
    id: UUID
    school_id: UUID
    embed_key: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WidgetStatusUpdate(BaseModel):
    status: str


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[UUID] = None
    visitor_id: str = "anonymous"
    language: str = "en"


class SourceResponse(BaseModel):
    doc_id: str
    breadcrumb: str
    source_file: Optional[str]
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceResponse]
    conversation_id: Optional[UUID]
    detected_language: str


class ConversationResponse(BaseModel):
    id: UUID
    visitor_id: str
    language: Optional[str]
    status: str
    started_at: datetime
    message_count: int

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: UUID
    sender_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
