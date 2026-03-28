"""Create user profile and memory system tables."""

import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text


async def create_tables():
    async with AsyncSessionLocal() as session:
        # Create user_profiles table
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL DEFAULT 'User',
                email VARCHAR(255),
                preferences JSONB DEFAULT '{}'::jsonb,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Create memory_files table
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS memory_files (
                id UUID PRIMARY KEY,
                user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                content TEXT DEFAULT '',
                description VARCHAR(500),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Create preference_tracking table
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS preference_tracking (
                id UUID PRIMARY KEY,
                user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
                key VARCHAR(255) NOT NULL,
                value TEXT NOT NULL,
                source VARCHAR(50) DEFAULT 'manual',
                confidence VARCHAR(20) DEFAULT 'medium',
                context TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # Create system_modifications table
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS system_modifications (
                id UUID PRIMARY KEY,
                user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
                conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
                modification_type VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id UUID,
                before_value JSONB,
                after_value JSONB,
                reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        await session.commit()
        print("Tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_tables())