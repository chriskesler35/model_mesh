"""FastAPI application entry point."""

import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# ─── Logging setup: write to logs/ directory so the UI log viewer works ────────
_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_log_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# stdout handler (keeps console output working as before)
_stdout_handler = logging.StreamHandler()
_stdout_handler.setLevel(logging.INFO)
_stdout_handler.setFormatter(_log_fmt)

# File handler — backend.log (stdout equivalent)
_file_handler = logging.FileHandler(_LOG_DIR / "backend.log", encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(_log_fmt)

# File handler — backend-error.log (WARNING+)
_err_handler = logging.FileHandler(_LOG_DIR / "backend-error.log", encoding="utf-8")
_err_handler.setLevel(logging.WARNING)
_err_handler.setFormatter(_log_fmt)

# Apply to root logger so every module's getLogger(__name__) inherits these
_root = logging.getLogger()
_root.setLevel(logging.INFO)
# Avoid duplicates if uvicorn already added a handler
if not _root.handlers:
    _root.addHandler(_stdout_handler)
_root.addHandler(_file_handler)
_root.addHandler(_err_handler)

# Ensure API keys from settings are available in os.environ for litellm
_key_map = {
    "ANTHROPIC_API_KEY": settings.anthropic_api_key,
    "GOOGLE_API_KEY": settings.google_api_key,
    "GEMINI_API_KEY": settings.gemini_api_key or settings.google_api_key,
    "OPENROUTER_API_KEY": settings.openrouter_api_key,
    "OPENAI_API_KEY": settings.openai_api_key,
}
for _k, _v in _key_map.items():
    if _v and not os.environ.get(_k):
        os.environ[_k] = _v
from app.database import engine, Base
from app.redis import close_redis
from app.routes import (
    health_router,
    models_router,
    personas_router,
    conversations_router,
    chat_router,
    stats_router,
)
from app.routes.user import router as user_router
from app.routes.models import router as models_crud_router
from app.routes.system import router as system_router
from app.routes.providers import router as providers_router
from app.routes.images import router as images_router, public_router as images_public_router
from app.routes.agents import router as agents_router
from app.routes.conversations import share_router
from app.routes.model_lookup import router as model_lookup_router
from app.routes.remote import router as remote_router
from app.routes.telegram_bot import router as telegram_router
from app.routes.identity import router as identity_router
from app.routes.workbench import router as workbench_router
from app.routes.pipelines import router as pipelines_router
from app.routes.projects import router as projects_router
from app.routes.runner import router as runner_router
from app.routes.custom_methods import router as custom_methods_router
from app.routes.methods import router as methods_router
from app.routes.metrics import router as metrics_router
from app.routes.marketplace import router as marketplace_router
from app.routes.skills import router as skills_router
from app.routes.sandbox import router as sandbox_router
from app.routes.collaboration import router as collab_router, public_router as auth_public_router
from app.routes.github_oauth import router as github_oauth_router
from app.routes.oauth_generic import router as oauth_generic_router
from app.routes.shares import router as shares_router, public_router as shares_public_router
from app.routes.hardware import router as hardware_router
from app.routes.api_keys import router as api_keys_router
from app.routes.model_validate import router as model_validate_router
from app.routes.tasks import router as tasks_router
from app.routes.model_sync import router as model_sync_router
from app.routes.context import router as context_router
from app.routes.preferences import router as preferences_router
from app.routes.app_settings import router as app_settings_router
from app.routes.workflows import router as workflows_router
from app.routes.audio import router as audio_router
from app.routes.websocket import router as websocket_router
from app.routes.feedback import router as feedback_router
from app.routes.learning import router as learning_router
from app.routes.custom_workflows import router as custom_workflows_router
from app.routes.notifications import router as notifications_router
from app.routes.websocket import router as websocket_router
from app.routes.runtime_capabilities import router as runtime_capabilities_router
from app.routes.chat_attachments import router as chat_attachments_router
from app.routes.tools import router as tools_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup — create tables then run column migrations
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.migrate import run_migrations
    await run_migrations()

    # Auto-cleanup conversations older than 30 days
    try:
        from app.database import AsyncSessionLocal as _ASL
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import select, delete
        from app.models import Conversation
        async with _ASL() as _db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            old = await _db.execute(
                select(Conversation).where(Conversation.keep_forever == False, Conversation.created_at < cutoff)
            )
            old_convs = old.scalars().all()
            if old_convs:
                for c in old_convs:
                    await _db.delete(c)
                await _db.commit()
                import logging
                logging.getLogger(__name__).info(f"Cleaned up {len(old_convs)} conversations older than 30 days")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Conversation cleanup failed: {e}")
    
    # Seed database with initial data
    from app.database import AsyncSessionLocal
    from app.seed import seed_database
    async with AsyncSessionLocal() as session:
        await seed_database(session)

    # Auto-sync Ollama models + key-gated paid models on every startup
    try:
        from app.routes.model_sync import run_model_sync
        async with AsyncSessionLocal() as session:
            result = await run_model_sync(session, deduplicate_existing=False)
            import logging as _log
            _log.getLogger(__name__).info(
                f"Startup model sync: {len(result['added'])} new, "
                f"ollama={'yes' if result['ollama_available'] else 'no'}"
            )
    except Exception as _e:
        import logging as _log
        _log.getLogger(__name__).warning(f"Startup model sync failed (non-fatal): {_e}")
    
    # Start Telegram polling (non-blocking background task)
    from app.routes.telegram_bot import start_polling as _start_telegram
    await _start_telegram()

    yield

    # Shutdown
    from app.routes.telegram_bot import stop_polling as _stop_telegram
    await _stop_telegram()
    await close_redis()


app = FastAPI(
    title="DevForgeAI",
    description="Intelligent AI platform for multi-agent orchestration and image generation",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus request metrics
from app.middleware.metrics_middleware import MetricsMiddleware
app.add_middleware(MetricsMiddleware)

# Include routers
app.include_router(health_router)
app.include_router(models_router)
app.include_router(models_crud_router)
app.include_router(personas_router)
app.include_router(conversations_router)
app.include_router(share_router)
app.include_router(chat_router)
app.include_router(stats_router)
app.include_router(user_router)
app.include_router(system_router)
app.include_router(providers_router)
app.include_router(images_router)
app.include_router(images_public_router)
app.include_router(agents_router)
app.include_router(model_lookup_router)
app.include_router(remote_router)
app.include_router(telegram_router)
app.include_router(identity_router)
app.include_router(workbench_router)
app.include_router(pipelines_router)
app.include_router(projects_router)
app.include_router(runner_router)
app.include_router(custom_methods_router)
app.include_router(methods_router)
app.include_router(marketplace_router)
app.include_router(skills_router)
app.include_router(sandbox_router)
app.include_router(collab_router)
app.include_router(auth_public_router)
app.include_router(github_oauth_router)
app.include_router(oauth_generic_router)
app.include_router(shares_router)
app.include_router(shares_public_router)
app.include_router(hardware_router)
app.include_router(api_keys_router)
app.include_router(model_validate_router)
app.include_router(tasks_router)
app.include_router(model_sync_router)
app.include_router(context_router)
app.include_router(preferences_router)
app.include_router(app_settings_router)
app.include_router(workflows_router)
app.include_router(audio_router)
app.include_router(websocket_router)
app.include_router(feedback_router)
app.include_router(learning_router)
app.include_router(custom_workflows_router)
app.include_router(notifications_router)
app.include_router(websocket_router)
app.include_router(runtime_capabilities_router)
app.include_router(chat_attachments_router)
app.include_router(tools_router)
app.include_router(metrics_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "DevForgeAI",
        "version": "0.2.0",
        "status": "running"
    }
