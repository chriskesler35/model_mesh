"""Seed database with default data."""

import asyncio
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Provider, Model, Persona


async def seed():
    """Seed the database with default providers, models, and personas."""
    async with AsyncSessionLocal() as session:
        # Check if providers exist
        result = await session.execute(select(Provider))
        if result.scalar_one_or_none():
            print("Database already seeded")
            return
        
        # Create providers
        ollama = Provider(
            id=uuid.uuid4(),
            name="ollama",
            display_name="Ollama (Local/Cloud)",
            api_base_url="http://localhost:11434",
            auth_type="none",
            is_active=True
        )
        anthropic = Provider(
            id=uuid.uuid4(),
            name="anthropic",
            display_name="Anthropic",
            auth_type="api_key",
            is_active=True
        )
        google = Provider(
            id=uuid.uuid4(),
            name="google",
            display_name="Google AI",
            auth_type="api_key",
            is_active=True
        )
        
        session.add_all([ollama, anthropic, google])
        await session.commit()
        
        # Create models
        models = [
            Model(
                id=uuid.uuid4(),
                provider_id=ollama.id,
                model_id="llama3",
                display_name="Llama 3",
                cost_per_1m_input=0,
                cost_per_1m_output=0,
                context_window=8192,
                capabilities={"streaming": True},
                is_active=True
            ),
            Model(
                id=uuid.uuid4(),
                provider_id=ollama.id,
                model_id="glm-4",
                display_name="GLM-4",
                cost_per_1m_input=0,
                cost_per_1m_output=0,
                context_window=8192,
                capabilities={"streaming": True},
                is_active=True
            ),
            Model(
                id=uuid.uuid4(),
                provider_id=anthropic.id,
                model_id="claude-sonnet-4-6",
                display_name="Claude Sonnet 4.6",
                cost_per_1m_input=3.0,
                cost_per_1m_output=15.0,
                context_window=200000,
                capabilities={"streaming": True, "vision": True},
                is_active=True
            ),
            Model(
                id=uuid.uuid4(),
                provider_id=google.id,
                model_id="gemini-2.5-pro",
                display_name="Gemini 2.5 Pro",
                cost_per_1m_input=1.25,
                cost_per_1m_output=5.0,
                context_window=1000000,
                capabilities={"streaming": True, "vision": True},
                is_active=True
            ),
        ]
        
        session.add_all(models)
        await session.commit()
        
        # Create default personas
        from datetime import datetime
        
        quick_helper = Persona(
            id=uuid.uuid4(),
            name="quick-helper",
            description="Quick helper for simple tasks",
            system_prompt="You are a helpful assistant. Be concise and direct.",
            primary_model_id=models[0].id,  # Llama 3
            fallback_model_id=models[2].id,  # Claude Sonnet
            routing_rules={"max_cost": 0.01, "prefer_local": True},
            memory_enabled=True,
            max_memory_messages=5,
            is_default=True,
            updated_at=datetime.utcnow().isoformat()
        )
        
        python_architect = Persona(
            id=uuid.uuid4(),
            name="python-architect",
            description="Expert Python code reviewer and architect",
            system_prompt="You are an expert Python architect. Review code for best practices, suggest improvements, and help design clean architectures.",
            primary_model_id=models[2].id,  # Claude Sonnet
            fallback_model_id=models[3].id,  # Gemini
            routing_rules={"max_cost": 0.05},
            memory_enabled=True,
            max_memory_messages=10,
            is_default=False,
            updated_at=datetime.utcnow().isoformat()
        )
        
        session.add_all([quick_helper, python_architect])
        await session.commit()
        
        print("Database seeded successfully!")
        print(f"Created 3 providers")
        print(f"Created {len(models)} models")
        print(f"Created 2 personas")
        print("\nDefault personas:")
        print("  - quick-helper (local-first, simple tasks)")
        print("  - python-architect (code review, Claude Sonnet primary)")


if __name__ == "__main__":
    asyncio.run(seed())