"""Phase 3 — Agentic Verifier.

Evaluates step outputs against their declared verification_checks and
determines whether an agentic plan run met the stated success criteria.

The current implementation applies lightweight pattern-matching rules
against the actual_output dict.  A future version can optionally use an
LLM call for semantic evaluation of open-ended criteria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Per-step result type
# ---------------------------------------------------------------------------


@dataclass
class StepVerificationResult:
    """Outcome of verifying a single plan step."""

    step_id: str
    passed: bool
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def verify_step(
    step_id: str,
    verification_checks: List[str],
    actual_output: Dict[str, Any],
) -> StepVerificationResult:
    """Evaluate actual_output against a list of verification checks.

    Supported check patterns (case-insensitive):

    * ``"<field> is present"`` / ``"non-empty"`` — asserts a named key is
      truthy in actual_output (falls back to "output" or "result" keys).
    * ``"completed without error"`` / ``"no error"`` — asserts that
      ``actual_output`` contains no "error" key and ``success`` is True-ish.
    * ``"<anything> pass"`` / ``"pass"`` — asserts
      ``actual_output["verification_result"] == "pass"``.
    * Any other text — passes if actual_output is non-empty (best-effort).
    """
    passed_checks: List[str] = []
    failed_checks: List[str] = []

    for check in verification_checks:
        check_lower = check.lower().strip()

        if " is present" in check_lower or "non-empty" in check_lower:
            # Extract the field name (first word before " is present")
            field_name = check_lower.replace(" is present", "").replace("non-empty", "").strip()
            field_name = field_name.split()[0] if field_name.split() else ""
            value = (
                actual_output.get(field_name)
                or actual_output.get("output")
                or actual_output.get("result")
            )
            (passed_checks if value else failed_checks).append(check)

        elif "without error" in check_lower or "no error" in check_lower:
            has_error = bool(actual_output.get("error"))
            is_success = actual_output.get("success", True)
            (passed_checks if (not has_error and is_success) else failed_checks).append(check)

        elif check_lower.endswith("pass") or check_lower == "pass":
            result_val = str(actual_output.get("verification_result", "")).lower()
            (passed_checks if result_val == "pass" else failed_checks).append(check)

        else:
            # Generic: passes as long as the output dict is non-empty
            (passed_checks if actual_output else failed_checks).append(check)

    return StepVerificationResult(
        step_id=step_id,
        passed=len(failed_checks) == 0,
        checks_passed=passed_checks,
        checks_failed=failed_checks,
        notes=f"{len(passed_checks)}/{len(verification_checks)} checks passed",
    )


def verify_plan_completion(
    plan_steps: List[Dict[str, Any]],
    step_outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify that all plan steps completed successfully.

    Parameters
    ----------
    plan_steps:
        List of step dicts (each must have ``step_id`` and
        ``verification_checks``).
    step_outputs:
        Map of step_id → actual output dict produced during execution.

    Returns
    -------
    dict
        ``passed``, ``steps_checked``, ``steps_passed``, and per-step
        ``step_results`` list.
    """
    results: list[Dict[str, Any]] = []

    for step in plan_steps:
        step_id = step.get("step_id", "")
        checks = step.get("verification_checks", [])
        output = step_outputs.get(step_id, {})
        result = verify_step(step_id, checks, output)
        results.append(
            {
                "step_id": step_id,
                "type": step.get("type", "unknown"),
                "passed": result.passed,
                "checks_passed": result.checks_passed,
                "checks_failed": result.checks_failed,
                "notes": result.notes,
            }
        )

    all_passed = all(r["passed"] for r in results)

    return {
        "passed": all_passed,
        "steps_checked": len(results),
        "steps_passed": sum(1 for r in results if r["passed"]),
        "step_results": results,
    }
