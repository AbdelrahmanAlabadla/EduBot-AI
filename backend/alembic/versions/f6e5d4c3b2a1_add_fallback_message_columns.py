"""add fallback_message_en and fallback_message_ar to chatbot_settings

Revision ID: f6e5d4c3b2a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-12 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6e5d4c3b2a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chatbot_settings', sa.Column('fallback_message_en', sa.Text(), nullable=True))
    op.add_column('chatbot_settings', sa.Column('fallback_message_ar', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('chatbot_settings', 'fallback_message_ar')
    op.drop_column('chatbot_settings', 'fallback_message_en')
