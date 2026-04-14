"""Add remaining 13 tables to align Alembic with ORM models

Revision ID: 005_remaining_tables
Revises: 004_conversation_shares
Create Date: 2026-04-09

Tables added:
  - agents
  - agent_memory
  - agent_runs
  - tasks
  - workbench_sessions
  - workbench_pipelines
  - workbench_phase_runs
  - workbench_commands
  - preferences
  - app_settings
  - custom_methods
  - learning_suggestions
  - notifications
  - custom_workflows
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '005_remaining_tables'
down_revision = '004_conversation_shares'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── agents ────────────────────────────────────────────────────────────
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('system_prompt', sa.Text, nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True)),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True)),
        sa.Column('method_phase', sa.String(50)),
        sa.Column('tools', postgresql.JSON, server_default='[]'),
        sa.Column('memory_enabled', sa.Boolean, server_default='true'),
        sa.Column('max_iterations', sa.Integer, server_default='10'),
        sa.Column('timeout_seconds', sa.Integer, server_default='300'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True)),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agents_method_phase', 'agents', ['method_phase'])

    # ── agent_memory ──────────────────────────────────────────────────────
    op.create_table(
        'agent_memory',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), nullable=False),
        sa.Column('run_id', sa.String(36)),
        sa.Column('task', sa.Text, nullable=False),
        sa.Column('output_summary', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agent_memory_agent_id', 'agent_memory', ['agent_id'])
    op.create_index('ix_agent_memory_agent_created', 'agent_memory', ['agent_id', 'created_at'])

    # ── agent_runs ────────────────────────────────────────────────────────
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task', sa.Text, nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='running'),
        sa.Column('output', sa.Text, server_default=''),
        sa.Column('tool_log', postgresql.JSON, server_default='[]'),
        sa.Column('input_tokens', sa.Integer, server_default='0'),
        sa.Column('output_tokens', sa.Integer, server_default='0'),
        sa.Column('duration_ms', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agent_runs_agent_id', 'agent_runs', ['agent_id'])

    # ── tasks ─────────────────────────────────────────────────────────────
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('params', postgresql.JSON, server_default='{}'),
        sa.Column('result', postgresql.JSON),
        sa.Column('error', sa.Text),
        sa.Column('progress', sa.Integer, server_default='0'),
        sa.Column('user_message', sa.String(500)),
        sa.Column('conversation_id', sa.String(36)),
        sa.Column('acknowledged', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ── workbench_sessions ────────────────────────────────────────────────
    op.create_table(
        'workbench_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('task', sa.Text, nullable=False),
        sa.Column('agent_type', sa.String(50), server_default='coder'),
        sa.Column('model', sa.String(200)),
        sa.Column('project_id', sa.String(36)),
        sa.Column('project_path', sa.Text),
        sa.Column('pipeline_id', sa.String(36)),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('files', postgresql.JSON, server_default='[]'),
        sa.Column('events_log', postgresql.JSON, server_default='[]'),
        sa.Column('messages', postgresql.JSON, server_default='[]'),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('estimated_cost', sa.Numeric(10, 6)),
        sa.Column('bypass_approvals', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
    )
    op.create_index('ix_workbench_sessions_pipeline_id', 'workbench_sessions', ['pipeline_id'])

    # ── workbench_pipelines ───────────────────────────────────────────────
    op.create_table(
        'workbench_pipelines',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('workbench_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('method_id', sa.String(50), nullable=False),
        sa.Column('phases', postgresql.JSON, nullable=False),
        sa.Column('current_phase_index', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', sa.String(30), server_default='pending'),
        sa.Column('auto_approve', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('approvers', postgresql.JSON),
        sa.Column('approval_policy', sa.String(20), server_default='any'),
        sa.Column('created_by', sa.String(100)),
        sa.Column('initial_task', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime),
    )

    # ── workbench_phase_runs ──────────────────────────────────────────────
    op.create_table(
        'workbench_phase_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('pipeline_id', sa.String(36), sa.ForeignKey('workbench_pipelines.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phase_index', sa.Integer, nullable=False),
        sa.Column('phase_name', sa.String(100), nullable=False),
        sa.Column('agent_role', sa.String(100), nullable=False),
        sa.Column('model_id', sa.String(200)),
        sa.Column('status', sa.String(30), server_default='pending'),
        sa.Column('input_context', postgresql.JSON),
        sa.Column('output_artifact', postgresql.JSON),
        sa.Column('raw_response', sa.Text),
        sa.Column('user_feedback', sa.Text),
        sa.Column('approvals', postgresql.JSON),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer, nullable=False, server_default='0'),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ── workbench_commands ────────────────────────────────────────────────
    op.create_table(
        'workbench_commands',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('workbench_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pipeline_id', sa.String(36)),
        sa.Column('phase_run_id', sa.String(36)),
        sa.Column('turn_number', sa.Integer),
        sa.Column('command', sa.Text, nullable=False),
        sa.Column('tier', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('exit_code', sa.Integer),
        sa.Column('stdout', sa.Text),
        sa.Column('stderr', sa.Text),
        sa.Column('user_feedback', sa.Text),
        sa.Column('bypass_used', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),
    )
    op.create_index('ix_workbench_commands_session_id', 'workbench_commands', ['session_id'])
    op.create_index('ix_workbench_commands_pipeline_id', 'workbench_commands', ['pipeline_id'])
    op.create_index('ix_workbench_commands_phase_run_id', 'workbench_commands', ['phase_run_id'])

    # ── preferences ───────────────────────────────────────────────────────
    op.create_table(
        'preferences',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('key', sa.String(200), nullable=False),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column('category', sa.String(100), server_default='general'),
        sa.Column('source', sa.String(50), server_default='detected'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ── app_settings ──────────────────────────────────────────────────────
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(200), primary_key=True),
        sa.Column('value', sa.Text),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ── custom_methods ────────────────────────────────────────────────────
    op.create_table(
        'custom_methods',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100)),
        sa.Column('name', sa.String(200), unique=True, nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('phases', postgresql.JSON, nullable=False),
        sa.Column('trigger_keywords', postgresql.JSON),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ── learning_suggestions ──────────────────────────────────────────────
    op.create_table(
        'learning_suggestions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('suggestion_type', sa.String(50), nullable=False),
        sa.Column('model_id', sa.String(200), nullable=False),
        sa.Column('task_type', sa.String(100)),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('current_value', sa.Text),
        sa.Column('suggested_value', sa.Text, nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('applied_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_learning_suggestions_model_id', 'learning_suggestions', ['model_id'])
    op.create_index('ix_learning_suggestions_task_type', 'learning_suggestions', ['task_type'])
    op.create_index('ix_learning_suggestions_status', 'learning_suggestions', ['status'])

    # ── notifications ─────────────────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('type', sa.String(50), nullable=False, server_default='mention'),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('message', sa.Text),
        sa.Column('conversation_id', sa.String(36)),
        sa.Column('message_id', sa.String(36)),
        sa.Column('read', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_conversation_id', 'notifications', ['conversation_id'])
    op.create_index('ix_notifications_read', 'notifications', ['read'])

    # ── custom_workflows ──────────────────────────────────────────────────
    op.create_table(
        'custom_workflows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100)),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('graph_data', postgresql.JSON, nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('custom_workflows')
    op.drop_table('notifications')
    op.drop_table('learning_suggestions')
    op.drop_table('custom_methods')
    op.drop_table('app_settings')
    op.drop_table('preferences')
    op.drop_table('workbench_commands')
    op.drop_table('workbench_phase_runs')
    op.drop_table('workbench_pipelines')
    op.drop_table('workbench_sessions')
    op.drop_table('tasks')
    op.drop_table('agent_runs')
    op.drop_table('agent_memory')
    op.drop_table('agents')
