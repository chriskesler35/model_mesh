"""Hardware monitoring — GPU VRAM, RAM, and model fitness checks."""

import subprocess
import logging
import httpx
from pathlib import Path
from fastapi import APIRouter, Depends
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/hardware", tags=["hardware"], dependencies=[Depends(verify_api_key)])

# Approximate VRAM requirements in MB (model_id pattern → VRAM needed)
# Based on 4-bit quantization estimates
MODEL_VRAM_MAP = {
    # Size tiers by parameter count in model name
    "0.6b": 800,   "1b": 1200,   "1.5b": 1500,  "3b": 2500,
    "7b":  5000,   "8b": 5500,   "13b": 9000,   "14b": 10000,
    "33b": 22000,  "34b": 23000, "32b": 21000,  "70b": 45000,
    # Named models
    "llama3.1:8b":                    5500,
    "glm-5:cloud":                    0,       # cloud — no local VRAM
    "minimax-m2.7:cloud":             0,
    "nemotron-3-super:cloud":         0,
    "qwen3:0.6b":                     800,
    "qwen2.5-coder:7b":               5000,
    "qwen2.5-coder:14b":              10000,
    "qwen2.5-coder:32b":              21000,
    "qwen2.5:14b-instruct-q4_K_M":   10000,
    "deepseek-coder:33b-instruct-q4_K_M": 22000,
    "yi:34b-chat-q4_K_M":            23000,
    "metal-muse-v1:latest":           5000,
    "metal-muse-v2:latest":           5000,
    "upcycled-qwen-coder-v1:latest":  10000,
    "upcycled-coder-v2:latest":       10000,
}

def _estimate_vram(model_id: str) -> int:
    """Estimate VRAM needed in MB for a model. Returns 0 for cloud models."""
    lower = model_id.lower()

    # Cloud models need no VRAM
    if ":cloud" in lower:
        return 0

    # Exact match first
    if model_id in MODEL_VRAM_MAP:
        return MODEL_VRAM_MAP[model_id]

    # Pattern match by size suffix
    for pattern, vram in MODEL_VRAM_MAP.items():
        if pattern in lower:
            return vram

    # Default estimate: assume 7B-equivalent if unknown
    return 5000


def _get_gpu_info() -> list[dict]:
    """Query nvidia-smi for per-GPU VRAM stats."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "index":       int(parts[0]),
                    "name":        parts[1],
                    "vram_total":  int(parts[2]),
                    "vram_used":   int(parts[3]),
                    "vram_free":   int(parts[4]),
                    "utilization": int(parts[5]) if parts[5].isdigit() else 0,
                    "temperature": int(parts[6]) if len(parts) > 6 and parts[6].isdigit() else 0,
                })
        return gpus
    except Exception as e:
        logger.warning(f"nvidia-smi failed: {e}")
        return []


async def _get_ollama_loaded() -> list[str]:
    """Get currently loaded models from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:11434/api/ps")
            if r.status_code == 200:
                return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


@router.get("/status")
async def hardware_status():
    """Full hardware status — GPUs, VRAM, loaded models."""
    gpus = _get_gpu_info()
    loaded = await _get_ollama_loaded()

    # Total free VRAM across all GPUs
    total_free = sum(g["vram_free"] for g in gpus)
    total_vram = sum(g["vram_total"] for g in gpus)

    return {
        "gpus": gpus,
        "total_vram_mb": total_vram,
        "total_free_mb": total_free,
        "total_used_mb": total_vram - total_free,
        "ollama_loaded": loaded,
        "gpu_count": len(gpus),
    }


@router.get("/check/{model_id:path}")
async def check_model_fitness(model_id: str):
    """
    Check if a model can run on this hardware.
    Returns: ok (bool), verdict, vram_needed_mb, vram_free_mb, recommendation
    """
    gpus = _get_gpu_info()
    loaded = await _get_ollama_loaded()

    # Cloud model — always OK
    lower = model_id.lower()
    is_cloud = ":cloud" in lower or model_id.startswith(("gpt-", "claude-", "gemini-", "anthropic/", "openai/", "openrouter/"))

    if is_cloud:
        return {
            "ok": True,
            "is_cloud": True,
            "verdict": "cloud",
            "label": "☁️ Cloud model",
            "detail": "No local GPU required — runs via API",
            "vram_needed_mb": 0,
            "vram_free_mb": sum(g["vram_free"] for g in gpus),
            "recommendation": None,
        }

    # Check if already loaded
    already_loaded = any(model_id in m for m in loaded)

    vram_needed = _estimate_vram(model_id)
    total_free = sum(g["vram_free"] for g in gpus)
    best_gpu_free = max((g["vram_free"] for g in gpus), default=0)

    # Determine fitness
    if not gpus:
        verdict = "unknown"
        label = "⚠️ No GPU detected"
        detail = "Could not read GPU info — model may still work via CPU (slow)"
        ok = False
    elif already_loaded:
        verdict = "loaded"
        label = "✅ Already loaded"
        detail = f"Model is currently in VRAM — ready to use"
        ok = True
    elif vram_needed == 0:
        verdict = "fits"
        label = "✅ Fits (minimal VRAM)"
        detail = "Very small model — fits easily"
        ok = True
    elif best_gpu_free >= vram_needed:
        pct = round(vram_needed / max(g["vram_total"] for g in gpus) * 100)
        verdict = "fits"
        label = f"✅ Fits ({pct}% of best GPU)"
        detail = f"Needs ~{vram_needed//1024}GB, {best_gpu_free//1024}GB free on best GPU"
        ok = True
    elif total_free >= vram_needed:
        verdict = "fits_split"
        label = "⚠️ Fits (split across GPUs)"
        detail = f"Needs ~{vram_needed//1024}GB total — may need multi-GPU mode"
        ok = True
    elif total_free >= vram_needed * 0.7:
        verdict = "tight"
        label = "⚠️ Tight — may work"
        detail = f"Needs ~{vram_needed//1024}GB, only {total_free//1024}GB free. Close other apps first."
        ok = False
    else:
        verdict = "too_large"
        label = "❌ Too large for current VRAM"
        detail = f"Needs ~{vram_needed//1024}GB, only {total_free//1024}GB free across all GPUs"
        ok = False

    # Suggest cloud alternative if too large
    recommendation = None
    if verdict in ("too_large", "tight"):
        recommendation = "Consider using a cloud version of this model, or unload other models from Ollama first."

    return {
        "ok": ok,
        "is_cloud": False,
        "verdict": verdict,
        "label": label,
        "detail": detail,
        "vram_needed_mb": vram_needed,
        "vram_free_mb": total_free,
        "best_gpu_free_mb": best_gpu_free,
        "already_loaded": already_loaded,
        "recommendation": recommendation,
        "gpus": gpus,
    }
