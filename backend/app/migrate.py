"""Simple SQLite migration - adds new columns to existing tables."""

import asyncio
import logging
from app.database import engine

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # agents table - persona support
    "ALTER TABLE agents ADD COLUMN persona_id VARCHAR(36)",
    "ALTER TABLE agents ADD COLUMN method_phase VARCHAR(50)",
    # conversations table - new session management columns
    "ALTER TABLE conversations ADD COLUMN title VARCHAR(200)",
    "ALTER TABLE conversations ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE conversations ADD COLUMN keep_forever BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE conversations ADD COLUMN last_message_at DATETIME",
    "ALTER TABLE conversations ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0",
    # workbench_sessions - token/cost tracking + event replay
    "ALTER TABLE workbench_sessions ADD COLUMN input_tokens INTEGER",
    "ALTER TABLE workbench_sessions ADD COLUMN output_tokens INTEGER",
    "ALTER TABLE workbench_sessions ADD COLUMN estimated_cost NUMERIC(10, 6)",
    "ALTER TABLE workbench_sessions ADD COLUMN events_log JSON",
    # workbench_sessions - conversational turns
    "ALTER TABLE workbench_sessions ADD COLUMN messages JSON",
    # workbench_sessions - link to pipeline (Option A multi-agent)
    "ALTER TABLE workbench_sessions ADD COLUMN pipeline_id VARCHAR(36)",
    # workbench_sessions - command execution bypass toggle
    "ALTER TABLE workbench_sessions ADD COLUMN bypass_approvals BOOLEAN NOT NULL DEFAULT 0",
    # workbench_commands audit table (created via create_all below)
    """CREATE TABLE IF NOT EXISTS workbench_commands (
        id VARCHAR(36) PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        pipeline_id VARCHAR(36),
        phase_run_id VARCHAR(36),
        turn_number INTEGER,
        command TEXT NOT NULL,
        tier VARCHAR(20) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        exit_code INTEGER,
        stdout TEXT,
        stderr TEXT,
        user_feedback TEXT,
        bypass_used BOOLEAN NOT NULL DEFAULT 0,
        duration_ms INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        started_at DATETIME,
        completed_at DATETIME,
        FOREIGN KEY (session_id) REFERENCES workbench_sessions(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_workbench_commands_session ON workbench_commands(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_workbench_commands_pipeline ON workbench_commands(pipeline_id)",
    "CREATE INDEX IF NOT EXISTS idx_workbench_commands_status ON workbench_commands(status)",
    # workbench_pipelines - collaborative approval support
    "ALTER TABLE workbench_pipelines ADD COLUMN approvers JSON",
    "ALTER TABLE workbench_pipelines ADD COLUMN approval_policy VARCHAR(20) DEFAULT 'any'",
    "ALTER TABLE workbench_pipelines ADD COLUMN created_by VARCHAR(100)",
    # workbench_phase_runs - retry + approval metadata
    "ALTER TABLE workbench_phase_runs ADD COLUMN approvals JSON",
    "ALTER TABLE workbench_phase_runs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE workbench_phase_runs ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE workbench_phase_runs ADD COLUMN input_tokens INTEGER",
    "ALTER TABLE workbench_phase_runs ADD COLUMN output_tokens INTEGER",
    # messages - inline image URL
    "ALTER TABLE messages ADD COLUMN image_url TEXT",
    # models - persisted live validation state
    "ALTER TABLE models ADD COLUMN validation_status VARCHAR(20) NOT NULL DEFAULT 'unverified'",
    "ALTER TABLE models ADD COLUMN validated_at DATETIME",
    "ALTER TABLE models ADD COLUMN validation_source VARCHAR(50)",
    "ALTER TABLE models ADD COLUMN validation_warning VARCHAR(500)",
    "ALTER TABLE models ADD COLUMN validation_error VARCHAR(500)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_models_provider_model_id ON models(provider_id, model_id)",
]


async def run_migrations():
    """Apply migrations, ignoring 'duplicate column' errors (idempotent)."""
    async with engine.begin() as conn:
        for sql in MIGRATIONS:
            try:
                await conn.execute(__import__('sqlalchemy').text(sql))
                logger.info(f"Migration OK: {sql[:60]}")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    logger.debug(f"Column already exists (skipped): {sql[:60]}")
                else:
                    logger.warning(f"Migration failed: {sql[:60]} - {e}")
    logger.info("Migrations complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migrations())
