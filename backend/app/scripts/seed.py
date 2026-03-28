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
            openrouter = Provider(
                id=uuid.uuid4(),
                name="openrouter",
                display_name="OpenRouter",
                api_base_url="https://openrouter.ai/api/v1",
                auth_type="api_key",
                is_active=True
            )

            session.add_all([ollama, anthropic, google, openrouter])
            await session.commit()
            print("Created 4 providers")
        
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
                # Ollama (local)
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["ollama"],
                    model_id="llama3.1:8b",
                    display_name="Llama 3.1 8B",
                    cost_per_1m_input=0,
                    cost_per_1m_output=0,
                    context_window=131072,
                    capabilities={"streaming": True},
                    is_active=True
                ),
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["ollama"],
                    model_id="glm-5:cloud",
                    display_name="GLM-5 Cloud",
                    cost_per_1m_input=0,
                    cost_per_1m_output=0,
                    context_window=131072,
                    capabilities={"streaming": True},
                    is_active=True
                ),
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["ollama"],
                    model_id="qwen2.5-coder:14b",
                    display_name="Qwen 2.5 Coder 14B",
                    cost_per_1m_input=0,
                    cost_per_1m_output=0,
                    context_window=131072,
                    capabilities={"streaming": True},
                    is_active=True
                ),
                # Anthropic
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
                    provider_id=providers["anthropic"],
                    model_id="claude-opus-4-20250514",
                    display_name="Claude Opus 4.6",
                    cost_per_1m_input=15.0,
                    cost_per_1m_output=75.0,
                    context_window=200000,
                    capabilities={"streaming": True, "vision": True},
                    is_active=True
                ),
                # Google
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
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["google"],
                    model_id="gemini-3.1-pro-preview",
                    display_name="Gemini 3.1 Pro Preview",
                    cost_per_1m_input=1.25,
                    cost_per_1m_output=5.0,
                    context_window=1000000,
                    capabilities={"streaming": True, "vision": True},
                    is_active=True
                ),
                # OpenRouter
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["openrouter"],
                    model_id="anthropic/claude-sonnet-4",
                    display_name="Claude Sonnet 4 (OpenRouter)",
                    cost_per_1m_input=3.0,
                    cost_per_1m_output=15.0,
                    context_window=200000,
                    capabilities={"streaming": True, "vision": True},
                    is_active=True
                ),
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["openrouter"],
                    model_id="anthropic/claude-opus-4",
                    display_name="Claude Opus 4 (OpenRouter)",
                    cost_per_1m_input=15.0,
                    cost_per_1m_output=75.0,
                    context_window=200000,
                    capabilities={"streaming": True, "vision": True},
                    is_active=True
                ),
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["openrouter"],
                    model_id="openai/gpt-4.1",
                    display_name="GPT-4.1 (OpenRouter)",
                    cost_per_1m_input=2.0,
                    cost_per_1m_output=8.0,
                    context_window=1000000,
                    capabilities={"streaming": True, "vision": True},
                    is_active=True
                ),
                Model(
                    id=uuid.uuid4(),
                    provider_id=providers["openrouter"],
                    model_id="google/gemini-3.1-pro-preview",
                    display_name="Gemini 3.1 Pro (OpenRouter)",
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
                description="Quick helper for simple tasks (local-first)",
                system_prompt="You are a helpful assistant. Be concise and direct.",
                primary_model_id=models_dict.get("llama3.1:8b"),
                fallback_model_id=models_dict.get("claude-sonnet-4-6"),
                routing_rules={"max_cost": 0.01, "prefer_local": True},
                memory_enabled=True,
                max_memory_messages=5,
                is_default=True,
                updated_at=datetime.utcnow()
            )

            # Classifier persona for auto-routing (uses cheap local model)
            classifier = Persona(
                id=uuid.uuid4(),
                name="classifier",
                description="Request classifier for intelligent routing",
                system_prompt="You classify requests into categories: CODE, MATH, CREATIVE, SIMPLE, or ANALYSIS. Reply with ONLY the category name.",
                primary_model_id=models_dict.get("llama3.1:8b"),
                fallback_model_id=models_dict.get("llama3.1:8b"),  # Same model, just needs to work
                routing_rules={"max_cost": 0.001, "prefer_local": True},
                memory_enabled=False,  # No memory needed for classification
                max_memory_messages=0,
                is_default=False,
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

            # Smart router persona with auto-routing enabled
            smart_router = Persona(
                id=uuid.uuid4(),
                name="smart-router",
                description="Intelligent router that classifies requests and selects optimal model",
                system_prompt="You are an intelligent assistant. Provide thoughtful responses.",
                primary_model_id=models_dict.get("claude-sonnet-4-6"),
                fallback_model_id=models_dict.get("llama3.1:8b"),
                routing_rules={
                    "max_cost": 0.10,
                    "auto_route": True,
                    "classifier_persona_id": str(classifier.id)  # Will be set after commit
                },
                memory_enabled=True,
                max_memory_messages=10,
                is_default=False,
                updated_at=datetime.utcnow()
            )

            # GLM-5 persona for code tasks
            glm_coder = Persona(
                id=uuid.uuid4(),
                name="glm-coder",
                description="Code assistant powered by GLM-5 (free local)",
                system_prompt="You are a coding assistant. Help with code, debugging, and technical questions.",
                primary_model_id=models_dict.get("glm-5:cloud"),
                fallback_model_id=models_dict.get("qwen2.5-coder:14b"),
                routing_rules={"max_cost": 0.01, "prefer_local": True},
                memory_enabled=True,
                max_memory_messages=10,
                is_default=False,
                updated_at=datetime.utcnow()
            )

            session.add_all([quick_helper, classifier, python_architect, smart_router, glm_coder])
            await session.commit()

            # Update smart_router with classifier_persona_id now that we have the ID
            smart_router.routing_rules["classifier_persona_id"] = str(classifier.id)
            await session.commit()

            print("Created 5 personas")

        print("\nSeed complete!")
        print("Default personas:")
        print("  - quick-helper (local-first, simple tasks)")
        print("  - classifier (request classifier for auto-routing)")
        print("  - python-architect (code review, Claude Sonnet primary)")
        print("  - smart-router (auto-routing with classification)")


if __name__ == "__main__":
    asyncio.run(seed())