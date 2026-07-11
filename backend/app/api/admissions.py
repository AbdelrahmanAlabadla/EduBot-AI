from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.admission_setting import AdmissionSetting
from app.schemas.admission import AdmissionSettingsResponse, AdmissionSettingsUpdate

router = APIRouter(prefix="/admission", tags=["Admission"])


def _get_or_create(db: Session, school_id):
    setting = db.query(AdmissionSetting).filter(AdmissionSetting.school_id == school_id).first()
    if not setting:
        setting = AdmissionSetting(school_id=school_id)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.get("/settings", response_model=AdmissionSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_or_create(db, current_user.school_id)


@router.put("/settings", response_model=AdmissionSettingsResponse)
def update_settings(
    payload: AdmissionSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    setting = _get_or_create(db, current_user.school_id)
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    return setting
