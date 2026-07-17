from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class DocumentResponse(BaseModel):
    id: UUID
    school_id: UUID
    name: str
    file_type: str
    file_path: str
    file_size: Optional[int]
    language: Optional[str]
    uploaded_by: Optional[UUID]
    status: str
    processing_result: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    chunk_text: str
    chunk_order: int
    chunk_type: Optional[str]
    breadcrumb: Optional[str]
    parent_id: Optional[UUID]
    searchable_text: Optional[str]
    qdrant_point_id: Optional[str]
    document_version: Optional[str]
    effective_date: Optional[datetime]
    chunk_metadata: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}
