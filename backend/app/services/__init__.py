"""Services package."""

from app.services.memory import MemoryManager, RedisUnavailableError
from app.services.model_client import model_client, ModelClient
from app.services.persona_resolver import PersonaResolver
from app.services.router import (
    Router,
    ModelMeshError,
    PersonaNotFoundError,
    NoModelAvailableError,
    AllModelsFailedError,
    CostLimitExceededError,
)
from app.services.agentic_state_machine import AgenticStateMachine
from app.services.agentic_events import build_agentic_event, compute_agentic_score
from app.services.agentic_goal import extract_goal
from app.services.agentic_planner import build_plan, summary_for_prompt
from app.services.agentic_verifier import verify_step, verify_plan_completion, StepVerificationResult
from app.services.agentic_orchestrator import AgenticOrchestrator

__all__ = [
    "MemoryManager",
    "RedisUnavailableError",
    "model_client",
    "ModelClient",
    "PersonaResolver",
    "Router",
    "ModelMeshError",
    "PersonaNotFoundError",
    "NoModelAvailableError",
    "AllModelsFailedError",
    "CostLimitExceededError",
    "AgenticStateMachine",
    "build_agentic_event",
    "compute_agentic_score",
    "extract_goal",
    "build_plan",
    "summary_for_prompt",
    "verify_step",
    "verify_plan_completion",
    "StepVerificationResult",
    "AgenticOrchestrator",
]