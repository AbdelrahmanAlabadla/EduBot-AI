from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.lead import Lead
from app.schemas.lead import LeadResponse, LeadStatusUpdate

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=list[LeadResponse])
def list_leads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Lead).filter(Lead.school_id == current_user.school_id).order_by(Lead.created_at.desc()).all()


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.school_id == current_user.school_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.put("/{lead_id}/status", response_model=LeadResponse)
def update_lead_status(
    lead_id: UUID,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.school_id == current_user.school_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if payload.status not in ("new", "contacted", "converted"):
        raise HTTPException(status_code=400, detail="Status must be one of: new, contacted, converted")
    lead.status = payload.status
    db.commit()
    db.refresh(lead)
    return lead
