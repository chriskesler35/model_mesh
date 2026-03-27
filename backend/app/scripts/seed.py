"""Seed database with default data."""

import asyncio
import uuid
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Provider, Model, Persona
from datetime import datetime


async def seed():
    """Seed the database with default providers, models, and personas."""
    async with AsyncSessionLocal() as session:
        # Check if providers exist
        result = await session.execute(select(Provider).limit(1))
        if result.scalar_one_or_none():
            print("Providers already seeded")
        else:
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
            print("Created 3 providers")
        
        # Get provider IDs
        providers_result = await session.execute(select(Provider))
        providers = {p.name: p.id for p in providers_result.scalars().all()}
        
        # Check if models exist
        result = await session.execute(select(Model).limit(1))
        if result.scalar_one_or_none():
            print("Models already seeded")
        else:
            # Create models
            models = [
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["ollama"],
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
                    provider_id=providers["ollama"],
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
                    provider_id=providers["anthropic"],
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
                    provider_id=providers["google"],
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
            print(f"Created {len(models)} models")
        
        # Get model IDs
        models_result = await session.execute(select(Model))
        models_list = models_result.scalars().all()
        models_dict = {m.model_id: m.id for m in models_list}
        
        # Check if personas exist
        result = await session.execute(select(Persona).limit(1))
        if result.scalar_one_or_none():
            print("Personas already seeded")
        else:
            # Create default personas
            quick_helper = Persona(
                id=uuid.uuid4(),
                name="quick-helper",
                description="Quick helper for simple tasks",
                system_prompt="You are a helpful assistant. Be concise and direct.",
                primary_model_id=models_dict.get("llama3"),
                fallback_model_id=models_dict.get("claude-sonnet-4-6"),
                routing_rules={"max_cost": 0.01, "prefer_local": True},
                memory_enabled=True,
                max_memory_messages=5,
                is_default=True,
                updated_at=datetime.utcnow()
            )
            
            python_architect = Persona(
                id=uuid.uuid4(),
                name="python-architect",
                description="Expert Python code reviewer and architect",
                system_prompt="You are an expert Python architect. Review code for best practices, suggest improvements, and help design clean architectures.",
                primary_model_id=models_dict.get("claude-sonnet-4-6"),
                fallback_model_id=models_dict.get("gemini-2.5-pro"),
                routing_rules={"max_cost": 0.05},
                memory_enabled=True,
                max_memory_messages=10,
                is_default=False,
                updated_at=datetime.utcnow()
            )
            
            session.add_all([quick_helper, python_architect])
            await session.commit()
            print("Created 2 personas")
        
        print("\nSeed complete!")
        print("Default personas:")
        print("  - quick-helper (local-first, simple tasks)")
        print("  - python-architect (code review, Claude Sonnet primary)")


if __name__ == "__main__":
    asyncio.run(seed())