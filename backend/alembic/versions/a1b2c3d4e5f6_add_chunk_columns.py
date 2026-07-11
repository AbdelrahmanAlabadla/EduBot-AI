"""add chunk_type breadcrumb parent_id searchable_text to document_chunks

Revision ID: a1b2c3d4e5f6
Revises: 7f59915912fe
Create Date: 2026-07-11 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7f59915912fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document_chunks', sa.Column('chunk_type', sa.String(length=20), nullable=True))
    op.add_column('document_chunks', sa.Column('breadcrumb', sa.String(length=500), nullable=True))
    op.add_column('document_chunks', sa.Column('parent_id', sa.UUID(), nullable=True))
    op.add_column('document_chunks', sa.Column('searchable_text', sa.Text(), nullable=True))
    op.create_foreign_key(
        'fk_document_chunks_parent_id',
        'document_chunks', 'document_chunks',
        ['parent_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_document_chunks_parent_id', 'document_chunks', type_='foreignkey')
    op.drop_column('document_chunks', 'searchable_text')
    op.drop_column('document_chunks', 'parent_id')
    op.drop_column('document_chunks', 'breadcrumb')
    op.drop_column('document_chunks', 'chunk_type')
