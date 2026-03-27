"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-03-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Providers table
    op.create_table(
        'providers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('api_base_url', sa.String(500)),
        sa.Column('auth_type', sa.String(50), default='none'),
        sa.Column('config', postgresql.JSONB, default={}),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_providers_name', 'providers', ['name'])
    
    # Models table
    op.create_table(
        'models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('display_name', sa.String(200)),
        sa.Column('cost_per_1m_input', sa.Numeric(10, 6), default=0),
        sa.Column('cost_per_1m_output', sa.Numeric(10, 6), default=0),
        sa.Column('context_window', sa.Integer),
        sa.Column('capabilities', postgresql.JSONB, default={}),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.UniqueConstraint('provider_id', 'model_id'),
    )
    
    # Personas table
    op.create_table(
        'personas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('system_prompt', sa.Text),
        sa.Column('primary_model_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('models.id', ondelete='SET NULL')),
        sa.Column('fallback_model_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('models.id', ondelete='SET NULL')),
        sa.Column('routing_rules', postgresql.JSONB, default={}),
        sa.Column('memory_enabled', sa.Boolean, default=True),
        sa.Column('max_memory_messages', sa.Integer, default=10),
        sa.Column('is_default', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_personas_name', 'personas', ['name'])
    op.create_index('ix_personas_default', 'personas', ['is_default'], postgresql_where=sa.text('is_default = true'))
    
    # Conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('personas.id', ondelete='SET NULL')),
        sa.Column('external_id', sa.String(100), unique=True),
        sa.Column('metadata', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('ix_conversations_persona', 'conversations', ['persona_id'])
    
    # Messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('model_used', postgresql.UUID(as_uuid=True), sa.ForeignKey('models.id', ondelete='SET NULL')),
        sa.Column('tokens_in', sa.Integer),
        sa.Column('tokens_out', sa.Integer),
        sa.Column('latency_ms', sa.Integer),
        sa.Column('estimated_cost', sa.Numeric(10, 6), default=0),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_messages_conversation', 'messages', ['conversation_id', sa.text('created_at DESC')])
    
    # Request logs table
    op.create_table(
        'request_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id', ondelete='SET NULL')),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('personas.id', ondelete='SET NULL')),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('models.id', ondelete='SET NULL')),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('providers.id', ondelete='SET NULL')),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('latency_ms', sa.Integer),
        sa.Column('estimated_cost', sa.Numeric(10, 6), default=0),
        sa.Column('success', sa.Boolean),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False),
    )
    op.create_index('idx_request_logs_created_at', 'request_logs', [sa.text('created_at DESC')])
    
    # Seed providers
    op.execute("""
        INSERT INTO providers (id, name, display_name, api_base_url, auth_type, is_active, created_at)
        VALUES 
            (uuid_generate_v4(), 'ollama', 'Ollama (Local/Cloud)', 'http://localhost:11434', 'none', true, NOW()),
            (uuid_generate_v4(), 'anthropic', 'Anthropic', NULL, 'api_key', true, NOW()),
            (uuid_generate_v4(), 'google', 'Google AI', NULL, 'api_key', true, NOW())
    """)


def downgrade() -> None:
    op.drop_table('request_logs')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('personas')
    op.drop_table('models')
    op.drop_table('providers')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')