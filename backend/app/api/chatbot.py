import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.chatbot_setting import ChatbotSetting
from app.models.chatbot_widget import ChatbotWidget
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.chatbot import (
    ChatbotSettingsResponse, ChatbotSettingsUpdate, WidgetResponse, WidgetStatusUpdate,
    ChatRequest, ChatResponse, SourceResponse, ConversationResponse, MessageResponse,
)
from app.pipeline.online_phase.pipeline import run_online_pipeline

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])


@router.get("/settings", response_model=ChatbotSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.school_id == current_user.school_id).first()
    if not setting:
        setting = ChatbotSetting(school_id=current_user.school_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.put("/settings", response_model=ChatbotSettingsResponse)
def update_settings(
    payload: ChatbotSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    setting = db.query(ChatbotSetting).filter(ChatbotSetting.school_id == current_user.school_id).first()
    if not setting:
        setting = ChatbotSetting(school_id=current_user.school_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    return setting


@router.post("/widget", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
def create_widget(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(ChatbotWidget).filter(ChatbotWidget.school_id == current_user.school_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Widget already exists for this school")
    widget = ChatbotWidget(
        school_id=current_user.school_id,
        embed_key=uuid.uuid4().hex,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return widget


@router.get("/widget", response_model=WidgetResponse)
def get_widget(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    widget = db.query(ChatbotWidget).filter(ChatbotWidget.school_id == current_user.school_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found. Create one first.")
    return widget


@router.put("/widget/status", response_model=WidgetResponse)
def update_widget_status(
    payload: WidgetStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    widget = db.query(ChatbotWidget).filter(ChatbotWidget.school_id == current_user.school_id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    if payload.status not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")
    widget.status = payload.status
    db.commit()
    db.refresh(widget)
    return widget


@router.post("/ask", response_model=ChatResponse)
def ask_question(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = run_online_pipeline(
        question=payload.question,
        school_id=current_user.school_id,
        visitor_id=payload.visitor_id,
        conversation_id=payload.conversation_id,
        language=payload.language,
        db=db,
    )
    return result


@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
):
    rows = (
        db.query(
            Conversation.id,
            Conversation.visitor_id,
            Conversation.language,
            Conversation.status,
            Conversation.started_at,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .filter(Conversation.school_id == current_user.school_id)
        .group_by(Conversation.id)
        .order_by(Conversation.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        ConversationResponse(
            id=r.id,
            visitor_id=r.visitor_id,
            language=r.language,
            status=r.status,
            started_at=r.started_at,
            message_count=r.message_count,
        )
        for r in rows
    ]


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
def get_conversation_messages(
    conv_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.school_id == current_user.school_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return messages


@router.post("/conversations/{conv_id}/close")
def close_conversation(
    conv_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.school_id == current_user.school_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.status = "closed"
    from datetime import datetime, timezone
    conv.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "closed"}
