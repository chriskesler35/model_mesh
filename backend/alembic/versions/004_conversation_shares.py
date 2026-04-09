"""Add conversation_shares table for shared conversation access.

Revision ID: 004_conversation_shares
Revises: 003_feedback
Create Date: 2026-04-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision = '004_conversation_shares'
down_revision = '003_feedback'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_shares',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('conversation_id', sa.String(36), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shared_with_user_id', sa.String(100), nullable=False),
        sa.Column('permission', sa.String(10), nullable=False, server_default='read'),
        sa.Column('token', sa.String(100), unique=True, nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_conversation_shares_conversation_id', 'conversation_shares', ['conversation_id'])
    op.create_index('ix_conversation_shares_shared_with_user_id', 'conversation_shares', ['shared_with_user_id'])
    op.create_index('ix_conversation_shares_token', 'conversation_shares', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_conversation_shares_token', table_name='conversation_shares')
    op.drop_index('ix_conversation_shares_shared_with_user_id', table_name='conversation_shares')
    op.drop_index('ix_conversation_shares_conversation_id', table_name='conversation_shares')
    op.drop_table('conversation_shares')
