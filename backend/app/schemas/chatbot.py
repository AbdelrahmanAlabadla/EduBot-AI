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


class WidgetResponse(BaseModel):
    id: UUID
    school_id: UUID
    embed_key: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WidgetStatusUpdate(BaseModel):
    status: str
