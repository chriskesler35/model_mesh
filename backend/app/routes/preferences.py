"""Preferences CRUD + detection endpoint."""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.preference import Preference

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/preferences", tags=["preferences"], dependencies=[Depends(verify_api_key)])


# ─── Schemas ──────────────────────────────────────────────────────────────────
class PreferenceCreate(BaseModel):
    key: str
    value: str
    category: str = "general"
    source: str = "manual"


class PreferenceUpdate(BaseModel):
    key: Optional[str] = None
    value: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class DetectRequest(BaseModel):
    """Ask the LLM to extract preferences from a conversation snippet."""
    messages: list[dict]  # [{role, content}, ...]
    model: Optional[str] = None


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_preferences(
    category: Optional[str] = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all preferences, optionally filtered by category."""
    query = select(Preference).order_by(desc(Preference.updated_at))
    if category:
        query = query.where(Preference.category == category)
    if not include_inactive:
        query = query.where(Preference.is_active == True)
    result = await db.execute(query)
    prefs = result.scalars().all()
    return {"data": [p.to_dict() for p in prefs], "total": len(prefs)}


@router.post("")
async def create_preference(body: PreferenceCreate, db: AsyncSession = Depends(get_db)):
    """Manually add a preference."""
    pref = Preference(
        id=str(uuid.uuid4()),
        key=body.key,
        value=body.value,
        category=body.category,
        source=body.source,
    )
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()


@router.patch("/{pref_id}")
async def update_preference(pref_id: str, body: PreferenceUpdate, db: AsyncSession = Depends(get_db)):
    """Update a preference (toggle, rename, recategorize)."""
    result = await db.execute(select(Preference).where(Preference.id == pref_id))
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    if body.key is not None:
        pref.key = body.key
    if body.value is not None:
        pref.value = body.value
    if body.category is not None:
        pref.category = body.category
    if body.is_active is not None:
        pref.is_active = body.is_active
    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()


@router.delete("/{pref_id}")
async def delete_preference(pref_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a preference permanently."""
    result = await db.execute(select(Preference).where(Preference.id == pref_id))
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    await db.delete(pref)
    await db.commit()
    return {"ok": True}


# ─── Detection ────────────────────────────────────────────────────────────────

DETECT_PROMPT = """You are a preference extraction system. Analyze the conversation below and extract any user preferences that the AI should remember for future interactions.

Return ONLY a JSON array of objects. Each object must have:
- "key": a short identifier (snake_case, 2-5 words max)
- "value": a clear one-sentence description of the preference
- "category": one of "general", "coding", "communication", "ui", "workflow"

Examples of preferences to look for:
- Communication style (brief vs detailed, formal vs casual)
- Code preferences (language, framework, style guide, indentation)
- UI preferences (dark mode, table format, emoji usage)
- Workflow preferences (always test first, prefer PRs, commit often)
- Content preferences (topics of interest, things to avoid)

If NO preferences are found, return an empty array: []
Do NOT invent preferences that aren't clearly stated or implied.
Only extract preferences the user explicitly states or strongly implies.

Conversation:
"""


@router.post("/detect")
async def detect_preferences(body: DetectRequest, db: AsyncSession = Depends(get_db)):
    """Use LLM to extract preferences from a conversation snippet."""
    import json
    from app.services.model_client import ModelClient
    from app.database import AsyncSessionLocal

    # Build conversation text
    conv_text = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in body.messages[-20:]  # last 20 messages max
    )

    # Resolve model
    model_id = body.model or "llama3.1:8b"
    from app.models.model import Model as ModelORM
    from app.models.provider import Provider as ProviderORM

    async with AsyncSessionLocal() as lookup_db:
        result = await lookup_db.execute(
            select(ModelORM, ProviderORM)
            .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
            .where(ModelORM.model_id == model_id)
            .limit(1)
        )
        row = result.first()
        if not row:
            # Fallback to first active model
            result = await lookup_db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.is_active == True)
                .limit(1)
            )
            row = result.first()

    if not row:
        raise HTTPException(status_code=500, detail="No model available for preference detection")

    model_orm, provider_orm = row

    client = ModelClient()
    try:
        response = await client.call_model(
            model=model_orm,
            provider=provider_orm,
            messages=[
                {"role": "system", "content": DETECT_PROMPT + conv_text},
                {"role": "user", "content": "Extract preferences from the conversation above. Return JSON array only."},
            ],
            stream=False,
            temperature=0.1,
            max_tokens=1000,
        )

        raw = response.choices[0].message.content.strip()
        # Parse JSON — handle markdown code blocks
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        detected = json.loads(raw)
        if not isinstance(detected, list):
            detected = []

    except Exception as e:
        logger.error(f"Preference detection failed: {e}")
        return {"detected": [], "saved": 0, "error": str(e)}

    # Save new preferences (skip duplicates by key)
    existing = await db.execute(select(Preference.key))
    existing_keys = {row[0] for row in existing.fetchall()}

    saved = 0
    results = []
    for item in detected:
        key = item.get("key", "").strip()
        value = item.get("value", "").strip()
        category = item.get("category", "general").strip()
        if not key or not value:
            continue
        if key in existing_keys:
            results.append({**item, "status": "skipped", "reason": "already exists"})
            continue

        pref = Preference(
            id=str(uuid.uuid4()),
            key=key,
            value=value,
            category=category,
            source="detected",
        )
        db.add(pref)
        existing_keys.add(key)
        saved += 1
        results.append({**item, "status": "saved"})

    await db.commit()
    return {"detected": results, "saved": saved}
