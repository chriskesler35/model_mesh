"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
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
from app.routes.images import router as images_router
from app.routes.agents import router as agents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
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

# Include routers
app.include_router(health_router)
app.include_router(models_router)
app.include_router(models_crud_router)
app.include_router(personas_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(stats_router)
app.include_router(user_router)
app.include_router(system_router)
app.include_router(providers_router)
app.include_router(images_router)
app.include_router(agents_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "DevForgeAI",
        "version": "0.2.0",
        "status": "running"
    }