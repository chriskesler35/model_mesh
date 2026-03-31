"""User profile and memory system endpoints."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import UserProfile, MemoryFile, SystemModification
from app.schemas.user_profile import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    MemoryFileCreate, MemoryFileUpdate, MemoryFileResponse, MemoryFileList,
    ModificationResponse, ModificationList
)
from app.middleware.auth import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["user"], dependencies=[Depends(verify_api_key)])


# ============================================================
# User Profile Endpoints
# ============================================================

@router.get("/user", response_model=UserProfileResponse)
async def get_user_profile(db: AsyncSession = Depends(get_db)):
    """Get or create the default user profile."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()
    
    if not profile:
        # Create default profile
        profile = UserProfile(
            id=uuid.uuid4(),
            name="User",
            preferences={}
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    
    return profile


@router.patch("/user", response_model=UserProfileResponse)
async def update_user_profile(
    updates: UserProfileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    if updates.name is not None:
        profile.name = updates.name
    if updates.email is not None:
        profile.email = updates.email
    if updates.preferences is not None:
        profile.preferences = updates.preferences
    
    await db.commit()
    await db.refresh(profile)
    return profile


# ============================================================
# Memory File Endpoints
# ============================================================

# These are managed exclusively by the Identity tab — never show in Memory
_IDENTITY_RESERVED = {"soul.md", "user.md", "identity.md", "SOUL.md", "USER.md", "IDENTITY.md"}


@router.get("/memory", response_model=MemoryFileList)
async def list_memory_files(db: AsyncSession = Depends(get_db)):
    """List all memory files for the user. Auto-seeds defaults if none exist."""
    from app.services.memory_context import MemoryContext
    ctx = MemoryContext(db)
    await ctx.get_or_create_user()

    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")

    result = await db.execute(
        select(MemoryFile).where(MemoryFile.user_id == profile.id)
    )
    # Filter out identity files — those belong to the Identity tab
    files = [f for f in result.scalars().all()
             if f.name not in _IDENTITY_RESERVED]

    return MemoryFileList(data=files, total=len(files))


@router.post("/memory", response_model=MemoryFileResponse)
async def create_memory_file(
    file: MemoryFileCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new memory file."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    memory_file = MemoryFile(
        id=uuid.uuid4(),
        user_id=profile.id,
        name=file.name,
        content=file.content,
        description=file.description
    )
    db.add(memory_file)
    await db.commit()
    await db.refresh(memory_file)
    return memory_file


@router.get("/memory/{file_id}", response_model=MemoryFileResponse)
async def get_memory_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific memory file."""
    result = await db.execute(
        select(MemoryFile).where(MemoryFile.id == uuid.UUID(file_id))
    )
    memory_file = result.scalar_one_or_none()
    
    if not memory_file:
        raise HTTPException(status_code=404, detail="Memory file not found")
    
    return memory_file


@router.patch("/memory/{file_id}", response_model=MemoryFileResponse)
async def update_memory_file(
    file_id: str,
    updates: MemoryFileUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a memory file."""
    result = await db.execute(
        select(MemoryFile).where(MemoryFile.id == uuid.UUID(file_id))
    )
    memory_file = result.scalar_one_or_none()
    
    if not memory_file:
        raise HTTPException(status_code=404, detail="Memory file not found")
    
    if updates.name is not None:
        memory_file.name = updates.name
    if updates.content is not None:
        memory_file.content = updates.content
    if updates.description is not None:
        memory_file.description = updates.description
    
    await db.commit()
    await db.refresh(memory_file)
    return memory_file


@router.delete("/memory/{file_id}")
async def delete_memory_file(
    file_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a memory file."""
    result = await db.execute(
        select(MemoryFile).where(MemoryFile.id == uuid.UUID(file_id))
    )
    memory_file = result.scalar_one_or_none()
    
    if not memory_file:
        raise HTTPException(status_code=404, detail="Memory file not found")
    
    await db.delete(memory_file)
    await db.commit()
    return {"status": "deleted"}


# ============================================================
# Preference Tracking Endpoints (MOVED to routes/preferences.py)
# The new Preference model supports categories, toggle, detection.
# Old PreferenceTracking endpoints removed to avoid route collision.
# ============================================================


# ============================================================
# System Modification Endpoints
# ============================================================

@router.get("/modifications", response_model=ModificationList)
async def list_modifications(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List system modifications (history of changes made through chat)."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    result = await db.execute(
        select(SystemModification)
        .where(SystemModification.user_id == profile.id)
        .order_by(SystemModification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    modifications = result.scalars().all()
    
    return ModificationList(data=modifications, total=len(modifications))