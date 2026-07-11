from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.school import School
from app.schemas.user import SetupSchema, UserCreate, UserLogin, UserResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup_first_school(payload: SetupSchema, db: Session = Depends(get_db)):
    existing_school = db.query(School).first()
    if existing_school:
        raise HTTPException(status_code=400, detail="Setup already completed")
    school = School(name=payload.school_name, slug=payload.school_slug)
    db.add(school)
    db.commit()
    db.refresh(school)
    user = User(
        name=payload.admin_name, email=payload.admin_email,
        password_hash=hash_password(payload.admin_password),
        school_id=school.id, role="super_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(data={"sub": str(user.id)})
    return {
        "school_id": str(school.id),
        "user_id": str(user.id),
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    school = db.query(School).filter(School.id == payload.school_id).first()
    if not school:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="School not found",
        )
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        school_id=payload.school_id,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
