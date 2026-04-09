"""Add feedback table for user satisfaction tracking.

Revision ID: 003_feedback
Revises: add_user_profile
Create Date: 2026-04-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision = '003_feedback'
down_revision = 'add_user_profile'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=True),
        sa.Column('message_id', sa.String(36), nullable=False),
        sa.Column('conversation_id', sa.String(36), nullable=True),
        sa.Column('model_id', sa.String(200), nullable=True),
        sa.Column('rating', sa.Integer, nullable=False),
        sa.Column('feedback_text', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_feedback_message_id', 'feedback', ['message_id'])
    op.create_index('ix_feedback_conversation_id', 'feedback', ['conversation_id'])
    op.create_index('ix_feedback_model_id', 'feedback', ['model_id'])


def downgrade() -> None:
    op.drop_index('ix_feedback_model_id', table_name='feedback')
    op.drop_index('ix_feedback_conversation_id', table_name='feedback')
    op.drop_index('ix_feedback_message_id', table_name='feedback')
    op.drop_table('feedback')
