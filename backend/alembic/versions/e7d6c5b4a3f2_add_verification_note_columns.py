"""add verification_note_en and verification_note_ar to chatbot_settings

Revision ID: e7d6c5b4a3f2
Revises: f6e5d4c3b2a1
Create Date: 2026-07-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7d6c5b4a3f2'
down_revision: Union[str, None] = 'f6e5d4c3b2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chatbot_settings', sa.Column('verification_note_en', sa.Text(), nullable=True))
    op.add_column('chatbot_settings', sa.Column('verification_note_ar', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('chatbot_settings', 'verification_note_ar')
    op.drop_column('chatbot_settings', 'verification_note_en')
