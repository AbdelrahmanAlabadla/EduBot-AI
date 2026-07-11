import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.chatbot_setting import ChatbotSetting
from app.models.chatbot_widget import ChatbotWidget
from app.schemas.chatbot import ChatbotSettingsResponse, ChatbotSettingsUpdate, WidgetResponse, WidgetStatusUpdate

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
