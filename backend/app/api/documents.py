import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session
from uuid import UUID
from app.database.connection import get_db
from app.dependencies.auth import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentResponse, DocumentChunkResponse
from app.pipeline.offline_phase.pipeline import run_offline_pipeline

router = APIRouter(prefix="/documents", tags=["Documents"])


def process_document_background(db: Session, doc_id: UUID):
    db = next(get_db())
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return
    try:
        doc.status = "processing"
        db.commit()
        run_offline_pipeline(
            file_path=doc.file_path,
            school_id=doc.school_id,
            document_id=doc.id,
            db=db,
        )
        doc.status = "completed"
        db.commit()
    except Exception as e:
        doc.status = "failed"
        doc.processing_result = str(e)
        db.commit()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    language: str = "en",
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed. Allowed: {settings.ALLOWED_FILE_TYPES}")
    content = file.file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds max size of {settings.MAX_UPLOAD_SIZE_MB}MB")
    upload_dir = Path(settings.UPLOAD_DIR) / str(current_user.school_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4()
    file_path = upload_dir / f"{file_id}.{ext}"
    with open(file_path, "wb") as f:
        f.write(content)
    doc = Document(
        school_id=current_user.school_id,
        name=file.filename,
        file_type=ext,
        file_path=str(file_path),
        file_size=len(content),
        language=language,
        uploaded_by=current_user.id,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    if background_tasks:
        background_tasks.add_task(process_document_background, db, doc.id)
    return doc


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Document).filter(Document.school_id == current_user.school_id).order_by(Document.created_at.desc()).all()


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.school_id == current_user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{doc_id}/chunks", response_model=list[DocumentChunkResponse])
def get_document_chunks(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.school_id == current_user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_order).all()


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.school_id == current_user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    db.delete(doc)
    db.commit()


@router.post("/{doc_id}/reprocess", response_model=DocumentResponse)
def reprocess_document(
    doc_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.school_id == current_user.school_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    doc.status = "uploaded"
    doc.processing_result = None
    db.commit()
    background_tasks.add_task(process_document_background, db, doc.id)
    return doc
