"""Routes package."""

from app.routes.health import router as health_router
from app.routes.models import router as models_router
from app.routes.personas import router as personas_router
from app.routes.conversations import router as conversations_router
from app.routes.chat import router as chat_router
from app.routes.stats import router as stats_router

__all__ = [
    "health_router",
    "models_router",
    "personas_router",
    "conversations_router",
    "chat_router",
    "stats_router",
]