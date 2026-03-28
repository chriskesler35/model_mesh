"""Add user profile and memory system tables.

Revision ID: add_user_profile
Revises: 
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = 'add_user_profile'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # User profiles table
    op.create_table(
        'user_profiles',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, server_default='User'),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('preferences', sa.JSON, server_default='{}'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Memory files table
    op.create_table(
        'memory_files',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('user_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('content', sa.Text, nullable=False, server_default=''),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Preference tracking table
    op.create_table(
        'preference_tracking',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('user_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column('source', sa.String(50), nullable=False, server_default='manual'),
        sa.Column('confidence', sa.String(20), server_default='medium'),
        sa.Column('context', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # System modifications table
    op.create_table(
        'system_modifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('user_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('modification_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', UUID(as_uuid=True), nullable=True),
        sa.Column('before_value', sa.JSON, nullable=True),
        sa.Column('after_value', sa.JSON, nullable=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index('ix_memory_files_user_id', 'memory_files', ['user_id'])
    op.create_index('ix_preference_tracking_user_id', 'preference_tracking', ['user_id'])
    op.create_index('ix_preference_tracking_key', 'preference_tracking', ['key'])
    op.create_index('ix_system_modifications_user_id', 'system_modifications', ['user_id'])


def downgrade():
    op.drop_index('ix_system_modifications_user_id', 'system_modifications')
    op.drop_index('ix_preference_tracking_key', 'preference_tracking')
    op.drop_index('ix_preference_tracking_user_id', 'preference_tracking')
    op.drop_index('ix_memory_files_user_id', 'memory_files')
    op.drop_table('system_modifications')
    op.drop_table('preference_tracking')
    op.drop_table('memory_files')
    op.drop_table('user_profiles')