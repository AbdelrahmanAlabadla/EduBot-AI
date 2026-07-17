import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from app.database.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_order = Column(Integer, nullable=False)
    chunk_type = Column(String(20), nullable=True)
    breadcrumb = Column(String(500), nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True)
    searchable_text = Column(Text, nullable=True)
    qdrant_point_id = Column(String(255), nullable=True)
    document_version = Column(String(50), nullable=True)
    effective_date = Column(DateTime(timezone=True), nullable=True)
    chunk_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")
    parent = relationship("DocumentChunk", remote_side="DocumentChunk.id", backref="children")
