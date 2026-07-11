"""add phase2 tables

Revision ID: 7f59915912fe
Revises: b39a6edc08b4
Create Date: 2026-07-10 22:48:28.341877

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7f59915912fe'
down_revision: Union[str, None] = 'b39a6edc08b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Indexes on existing tables
    op.create_index('ix_schools_status', 'schools', ['status'])
    op.create_index('ix_schools_created_at', 'schools', ['created_at'])
    op.create_index('ix_users_school_id', 'users', ['school_id'])
    op.create_index('ix_users_role', 'users', ['role'])
    op.create_index('ix_users_school_id_role', 'users', ['school_id', 'role'])

    # admission_settings
    op.create_table('admission_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('collect_student_name', sa.Boolean(), nullable=True),
        sa.Column('collect_parent_name', sa.Boolean(), nullable=True),
        sa.Column('collect_email', sa.Boolean(), nullable=True),
        sa.Column('collect_phone', sa.Boolean(), nullable=True),
        sa.Column('collect_student_grade', sa.Boolean(), nullable=True),
        sa.Column('collect_interested_program', sa.Boolean(), nullable=True),
        sa.Column('collect_visit_request', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id'),
    )

    # analytics_events
    op.create_table('analytics_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=True),
        sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_analytics_events_school_id', 'analytics_events', ['school_id'])
    op.create_index('ix_analytics_events_event_type', 'analytics_events', ['event_type'])
    op.create_index('ix_analytics_events_school_event', 'analytics_events', ['school_id', 'event_type'])
    op.create_index('ix_analytics_events_school_created', 'analytics_events', ['school_id', 'created_at'])

    # chatbot_settings
    op.create_table('chatbot_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('chatbot_name', sa.String(length=255), nullable=True),
        sa.Column('welcome_message', sa.Text(), nullable=True),
        sa.Column('default_language', sa.String(length=10), nullable=True),
        sa.Column('supported_languages', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('avatar_url', sa.String(length=500), nullable=True),
        sa.Column('theme_color', sa.String(length=20), nullable=True),
        sa.Column('collect_contact_info', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('school_id'),
    )

    # chatbot_widgets
    op.create_table('chatbot_widgets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('embed_key', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('embed_key'),
    )

    # conversations
    op.create_table('conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('visitor_id', sa.String(length=255), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversations_school_id', 'conversations', ['school_id'])
    op.create_index('ix_conversations_visitor_id', 'conversations', ['visitor_id'])
    op.create_index('ix_conversations_status', 'conversations', ['status'])
    op.create_index('ix_conversations_school_created', 'conversations', ['school_id', 'created_at'])

    # documents
    op.create_table('documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('processing_result', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_school_id', 'documents', ['school_id'])
    op.create_index('ix_documents_school_status', 'documents', ['school_id', 'status'])

    # leads
    op.create_table('leads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('student_grade', sa.String(length=50), nullable=True),
        sa.Column('interested_program', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_leads_school_id', 'leads', ['school_id'])
    op.create_index('ix_leads_school_status', 'leads', ['school_id', 'status'])

    # messages
    op.create_table('messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('sender_type', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('token_usage', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_conv_created', 'messages', ['conversation_id', 'created_at'])

    # document_chunks
    op.create_table('document_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('school_id', sa.UUID(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_order', sa.Integer(), nullable=False),
        sa.Column('qdrant_point_id', sa.String(length=255), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_chunks_document_id', 'document_chunks', ['document_id'])
    op.create_index('ix_document_chunks_school_id', 'document_chunks', ['school_id'])
    op.create_index('ix_document_chunks_doc_order', 'document_chunks', ['document_id', 'chunk_order'])


def downgrade() -> None:
    op.drop_index('ix_document_chunks_doc_order', table_name='document_chunks')
    op.drop_index('ix_document_chunks_school_id', table_name='document_chunks')
    op.drop_index('ix_document_chunks_document_id', table_name='document_chunks')
    op.drop_table('document_chunks')
    op.drop_index('ix_messages_conv_created', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_leads_school_status', table_name='leads')
    op.drop_index('ix_leads_school_id', table_name='leads')
    op.drop_table('leads')
    op.drop_index('ix_documents_school_status', table_name='documents')
    op.drop_index('ix_documents_school_id', table_name='documents')
    op.drop_table('documents')
    op.drop_index('ix_conversations_school_created', table_name='conversations')
    op.drop_index('ix_conversations_status', table_name='conversations')
    op.drop_index('ix_conversations_visitor_id', table_name='conversations')
    op.drop_index('ix_conversations_school_id', table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('chatbot_widgets')
    op.drop_table('chatbot_settings')
    op.drop_index('ix_analytics_events_school_created', table_name='analytics_events')
    op.drop_index('ix_analytics_events_school_event', table_name='analytics_events')
    op.drop_index('ix_analytics_events_event_type', table_name='analytics_events')
    op.drop_index('ix_analytics_events_school_id', table_name='analytics_events')
    op.drop_table('analytics_events')
    op.drop_table('admission_settings')
    op.drop_index('ix_users_school_id_role', table_name='users')
    op.drop_index('ix_users_role', table_name='users')
    op.drop_index('ix_users_school_id', table_name='users')
    op.drop_index('ix_schools_created_at', table_name='schools')
    op.drop_index('ix_schools_status', table_name='schools')
