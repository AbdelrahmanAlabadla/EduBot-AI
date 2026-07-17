"""add document_version and effective_date to document_chunks

Revision ID: f7a8b9c0d1e2
Revises: e7d6c5b4a3f2
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'e7d6c5b4a3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_chunks', sa.Column('document_version', sa.String(length=50), nullable=True))
    op.add_column('document_chunks', sa.Column('effective_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('document_chunks', 'effective_date')
    op.drop_column('document_chunks', 'document_version')
