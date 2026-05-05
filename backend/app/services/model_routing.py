"""Model routing policy and preview selection helpers."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting
from app.models.model import Model
from app.models.provider import Provider

POLICY_SETTING_KEY = "model_routing_policy_json"

DEFAULT_ROUTING_POLICY: dict[str, Any] = {
    "version": 1,
    "defaults": {
        "budget_mode": "balanced",
        "risk_level": "normal",
        "latency_priority": "balanced",
        "max_candidates": 5,
    },
    "task_profiles": {
        "chat": {"preferred_capabilities": ["chat", "streaming"]},
        "coding": {"preferred_capabilities": ["chat", "streaming", "code"]},
        "analysis": {"preferred_capabilities": ["chat", "streaming"]},
        "planning": {"preferred_capabilities": ["chat", "streaming"]},
    },
    "provider_preferences": {
        "balanced": ["openrouter", "github-copilot", "openai", "anthropic", "google", "ollama"],
        "cost_saver": ["openrouter", "google", "ollama", "openai", "anthropic", "github-copilot"],
        "high_quality": ["anthropic", "openai", "github-copilot", "openrouter", "google", "ollama"],
    },
}


def _normalize_capabilities(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    out = set()
    for key, enabled in value.items():
        if enabled:
            out.add(str(key).lower().strip())
    return out


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def get_routing_policy(db: AsyncSession) -> dict[str, Any]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == POLICY_SETTING_KEY))).scalar_one_or_none()
    if not row or not row.value:
        return json.loads(json.dumps(DEFAULT_ROUTING_POLICY))
    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_ROUTING_POLICY))


async def set_routing_policy(db: AsyncSession, policy: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(policy, ensure_ascii=True)
    row = (await db.execute(select(AppSetting).where(AppSetting.key == POLICY_SETTING_KEY))).scalar_one_or_none()
    if row:
        row.value = serialized
    else:
        row = AppSetting(key=POLICY_SETTING_KEY, value=serialized)
        db.add(row)
    await db.commit()
    return policy


async def preview_route(
    db: AsyncSession,
    *,
    task_type: str = "chat",
    prompt_preview: str = "",
    risk_level: str = "normal",
    budget_mode: str = "balanced",
    latency_priority: str = "balanced",
    preferred_provider: str | None = None,
) -> dict[str, Any]:
    policy = await get_routing_policy(db)
    defaults = policy.get("defaults") if isinstance(policy, dict) else {}

    resolved_budget_mode = (budget_mode or defaults.get("budget_mode") or "balanced").strip().lower()
    resolved_risk = (risk_level or defaults.get("risk_level") or "normal").strip().lower()
    resolved_latency = (latency_priority or defaults.get("latency_priority") or "balanced").strip().lower()

    task_profiles = policy.get("task_profiles") if isinstance(policy, dict) else {}
    task_profile = task_profiles.get(task_type, task_profiles.get("chat", {})) if isinstance(task_profiles, dict) else {}
    required_caps = {str(c).lower().strip() for c in (task_profile.get("preferred_capabilities") or [])}

    rows = (
        await db.execute(
            select(Model, Provider)
            .join(Provider, Model.provider_id == Provider.id)
            .where(Model.is_active == True)
            .where(Model.validation_status == "validated")
            .where(Provider.is_active == True)
        )
    ).all()

    estimated_tokens = max(len((prompt_preview or "").strip()) // 4, 1)

    preferences = policy.get("provider_preferences") if isinstance(policy, dict) else {}
    pref_list = preferences.get(resolved_budget_mode) if isinstance(preferences, dict) else None
    if not isinstance(pref_list, list):
        pref_list = DEFAULT_ROUTING_POLICY["provider_preferences"]["balanced"]
    provider_priority = {name: idx for idx, name in enumerate(pref_list)}

    scored: list[dict[str, Any]] = []
    for model, provider in rows:
        provider_name = (provider.name or "").lower().strip()
        if preferred_provider and provider_name != preferred_provider.lower().strip():
            continue

        caps = _normalize_capabilities(model.capabilities)
        if required_caps and not required_caps.issubset(caps):
            continue

        input_cost = _to_float(model.cost_per_1m_input)
        output_cost = _to_float(model.cost_per_1m_output)
        blended_cost = input_cost + output_cost
        est_cost = ((estimated_tokens / 1_000_000.0) * input_cost) + ((estimated_tokens / 1_000_000.0) * output_cost)

        # Lower score is better.
        cost_rank = blended_cost
        if resolved_budget_mode in {"cost_saver", "cheap", "low"}:
            cost_rank = blended_cost * 0.6
        elif resolved_budget_mode in {"high_quality", "quality"}:
            cost_rank = blended_cost * 1.3

        quality_bias = 0.0
        if resolved_risk in {"high", "high_accuracy", "critical"}:
            quality_bias = -blended_cost * 0.25

        latency_penalty = 0.0
        if resolved_latency in {"low", "fast"}:
            latency_penalty = (model.context_window or 0) / 10_000_000

        provider_rank = provider_priority.get(provider_name, len(provider_priority) + 5)
        final_score = provider_rank + cost_rank + latency_penalty + quality_bias

        scored.append(
            {
                "score": final_score,
                "provider_rank": provider_rank,
                "blended_cost_per_1m": round(blended_cost, 6),
                "estimated_cost": round(est_cost, 8),
                "model_id": model.model_id,
                "display_name": model.display_name or model.model_id,
                "provider": provider.name,
                "context_window": model.context_window,
                "capabilities": sorted(list(caps)),
                "reason": [
                    f"task={task_type}",
                    f"budget_mode={resolved_budget_mode}",
                    f"risk_level={resolved_risk}",
                    f"latency={resolved_latency}",
                ],
            }
        )

    scored.sort(key=lambda item: item["score"])
    top = scored[:5]

    return {
        "request": {
            "task_type": task_type,
            "budget_mode": resolved_budget_mode,
            "risk_level": resolved_risk,
            "latency_priority": resolved_latency,
            "preferred_provider": preferred_provider,
            "estimated_input_tokens": estimated_tokens,
        },
        "selected": top[0] if top else None,
        "alternatives": top[1:] if len(top) > 1 else [],
        "policy": policy,
    }
