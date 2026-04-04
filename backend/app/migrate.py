"""Simple SQLite migration - adds new columns to existing tables."""

import asyncio
import logging
from app.database import engine

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # agents table - persona support
    "ALTER TABLE agents ADD COLUMN persona_id VARCHAR(36)",
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
    # messages - inline image URL
    "ALTER TABLE messages ADD COLUMN image_url TEXT",
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
