"""
generate_report.py — Parses pytest JSON + Playwright JSON results and generates
a structured Markdown report with a prioritized fix-it list.

Usage:
    python generate_report.py <pytest_json> <e2e_json> <pytest_log> <e2e_log> <output_md> <timestamp>
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime


def load_json(path):
    """Load JSON file, return None if missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def parse_pytest_results(data):
    """Parse pytest-json-report output into structured results."""
    if not data:
        return {"passed": [], "failed": [], "errors": [], "skipped": [], "warnings": [],
                "total": 0, "duration": 0, "summary": "No pytest results found"}

    tests = data.get("tests", [])
    summary = data.get("summary", {})

    passed = []
    failed = []
    errors = []
    skipped = []

    for t in tests:
        outcome = t.get("outcome", "unknown")
        entry = {
            "nodeid": t.get("nodeid", "unknown"),
            "duration": round(t.get("duration", 0), 3),
            "outcome": outcome,
        }

        # Extract failure details
        if outcome in ("failed", "error"):
            call = t.get("call", {})
            setup = t.get("setup", {})
            # Get the crash/longrepr info
            crash = call.get("crash", setup.get("crash", {}))
            longrepr = call.get("longrepr", setup.get("longrepr", ""))

            entry["message"] = crash.get("message", "")
            entry["file"] = crash.get("path", "")
            entry["lineno"] = crash.get("lineno", 0)

            # Get full traceback
            if isinstance(longrepr, str):
                entry["traceback"] = longrepr
            elif isinstance(longrepr, dict):
                entry["traceback"] = longrepr.get("reprcrash", {}).get("message", "")
            else:
                entry["traceback"] = str(longrepr) if longrepr else ""

        if outcome == "passed":
            passed.append(entry)
        elif outcome == "failed":
            failed.append(entry)
        elif outcome == "error":
            errors.append(entry)
        elif outcome == "skipped":
            entry["reason"] = ""
            # Try to extract skip reason
            setup = t.get("setup", {})
            call = t.get("call", {})
            for phase in [setup, call]:
                longrepr = phase.get("longrepr", "")
                if isinstance(longrepr, str) and longrepr:
                    entry["reason"] = longrepr
                    break
            skipped.append(entry)

    duration = data.get("duration", 0)

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "total": len(tests),
        "duration": round(duration, 2),
        "summary": f"{len(passed)} passed, {len(failed)} failed, {len(errors)} errors, {len(skipped)} skipped"
    }


def parse_playwright_results(data):
    """Parse Playwright JSON report into structured results."""
    if not data:
        return {"passed": [], "failed": [], "skipped": [], "total": 0,
                "duration": 0, "summary": "No Playwright results found"}

    suites = data.get("suites", [])
    passed = []
    failed = []
    skipped = []

    def walk_suites(suites, prefix=""):
        for suite in suites:
            suite_title = suite.get("title", "")
            full_prefix = f"{prefix} > {suite_title}" if prefix else suite_title

            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        entry = {
                            "name": f"{full_prefix} > {spec.get('title', '')}",
                            "status": result.get("status", "unknown"),
                            "duration": round(result.get("duration", 0) / 1000, 3),  # ms to seconds
                        }

                        if result.get("status") == "failed":
                            # Get error message
                            error = result.get("error", {})
                            entry["message"] = error.get("message", "")
                            entry["snippet"] = error.get("snippet", "")
                            # Attachments (screenshots)
                            attachments = result.get("attachments", [])
                            entry["screenshots"] = [a.get("path", "") for a in attachments
                                                    if a.get("contentType", "").startswith("image/")]
                            failed.append(entry)
                        elif result.get("status") == "passed":
                            passed.append(entry)
                        elif result.get("status") in ("skipped", "timedOut"):
                            skipped.append(entry)

            # Recurse into nested suites
            walk_suites(suite.get("suites", []), full_prefix)

    walk_suites(suites)

    total = len(passed) + len(failed) + len(skipped)
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "duration": sum(t["duration"] for t in passed + failed + skipped),
        "summary": f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped"
    }


def categorize_failure(nodeid):
    """Map a test node ID to a feature area for the fix-it list."""
    nodeid_lower = nodeid.lower()
    categories = {
        "health": "Health & System",
        "model": "Models",
        "persona": "Personas",
        "conversation": "Conversations",
        "chat": "Chat / LLM",
        "agent": "Agents",
        "image": "Image Generation / Gallery",
        "gallery": "Image Generation / Gallery",
        "project": "Projects",
        "workbench": "Workbench",
        "identity": "Identity / Onboarding",
        "method": "Development Methods",
        "collab": "Collaboration",
        "preference": "Learned Preferences",
        "setting": "Settings",
        "api_key": "Settings",
        "stat": "Stats / Analytics",
        "remote": "Remote Access",
        "telegram": "Telegram Bot",
        "workflow": "ComfyUI / Workflows",
        "comfyui": "ComfyUI / Workflows",
        "task": "Tasks",
        "context": "Context / Memory",
        "hardware": "Hardware",
        "user": "User Profile",
        "memory": "Memory Files",
        "provider": "Providers",
        "sandbox": "Sandbox / Isolation",
        "navigation": "Navigation / UI",
        "dark": "Dark Mode / Theming",
        "error": "Error Handling",
        "dashboard": "Dashboard",
    }
    for key, category in categories.items():
        if key in nodeid_lower:
            return category
    return "Other"


def severity_from_category(category):
    """Assign severity based on feature area."""
    critical = ["Health & System", "Chat / LLM", "Models", "Conversations"]
    high = ["Agents", "Workbench", "Image Generation / Gallery", "Projects",
            "Identity / Onboarding", "Settings"]
    medium = ["Personas", "Stats / Analytics", "Remote Access", "Telegram Bot",
              "Learned Preferences", "Development Methods"]
    # Everything else is low

    if category in critical:
        return "🔴 CRITICAL"
    elif category in high:
        return "🟠 HIGH"
    elif category in medium:
        return "🟡 MEDIUM"
    return "🟢 LOW"


def generate_report(pytest_results, pw_results, pytest_log_path, e2e_log_path, timestamp):
    """Generate the full markdown report."""
    lines = []

    # Header
    lines.append(f"# DevForgeAI Test Report")
    lines.append(f"")
    lines.append(f"**Generated:** {timestamp.replace('_', ' ')}")
    lines.append(f"**Machine:** {os.environ.get('COMPUTERNAME', 'unknown')}")
    lines.append(f"**Backend:** http://localhost:19000")
    lines.append(f"**Frontend:** http://localhost:3001")
    lines.append(f"")

    # ---- EXECUTIVE SUMMARY ----
    total_pass = len(pytest_results["passed"]) + len(pw_results["passed"])
    total_fail = len(pytest_results["failed"]) + len(pw_results["failed"])
    total_error = len(pytest_results["errors"])
    total_skip = len(pytest_results["skipped"]) + len(pw_results["skipped"])
    total_all = pytest_results["total"] + pw_results["total"]
    pass_rate = (total_pass / total_all * 100) if total_all > 0 else 0

    if total_fail == 0 and total_error == 0:
        verdict = "✅ ALL TESTS PASSED"
    elif total_fail + total_error <= 5:
        verdict = "⚠️ MINOR ISSUES FOUND"
    elif total_fail + total_error <= 20:
        verdict = "🟠 ISSUES FOUND — NEEDS ATTENTION"
    else:
        verdict = "🔴 SIGNIFICANT FAILURES — FIX REQUIRED"

    lines.append(f"## Executive Summary")
    lines.append(f"")
    lines.append(f"**Verdict: {verdict}**")
    lines.append(f"")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total tests run | {total_all} |")
    lines.append(f"| ✅ Passed | {total_pass} |")
    lines.append(f"| ❌ Failed | {total_fail} |")
    lines.append(f"| 💥 Errors | {total_error} |")
    lines.append(f"| ⏭️ Skipped | {total_skip} |")
    lines.append(f"| Pass rate | {pass_rate:.1f}% |")
    lines.append(f"| Backend API tests | {pytest_results['summary']} |")
    lines.append(f"| Frontend E2E tests | {pw_results['summary']} |")
    lines.append(f"| Total duration | {pytest_results['duration'] + pw_results['duration']:.1f}s |")
    lines.append(f"")

    # ---- FIX-IT LIST ----
    all_failures = []

    for f in pytest_results["failed"]:
        all_failures.append({
            "source": "API",
            "test": f["nodeid"],
            "category": categorize_failure(f["nodeid"]),
            "message": f.get("message", ""),
            "file": f.get("file", ""),
            "lineno": f.get("lineno", 0),
            "traceback": f.get("traceback", ""),
        })

    for f in pytest_results["errors"]:
        all_failures.append({
            "source": "API",
            "test": f["nodeid"],
            "category": categorize_failure(f["nodeid"]),
            "message": f.get("message", ""),
            "file": f.get("file", ""),
            "lineno": f.get("lineno", 0),
            "traceback": f.get("traceback", ""),
        })

    for f in pw_results["failed"]:
        all_failures.append({
            "source": "E2E",
            "test": f["name"],
            "category": categorize_failure(f["name"]),
            "message": f.get("message", ""),
            "file": "",
            "lineno": 0,
            "traceback": f.get("snippet", ""),
        })

    if all_failures:
        # Group by category
        by_category = {}
        for f in all_failures:
            cat = f["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(f)

        # Sort categories by severity
        severity_order = {"🔴 CRITICAL": 0, "🟠 HIGH": 1, "🟡 MEDIUM": 2, "🟢 LOW": 3}
        sorted_cats = sorted(by_category.keys(),
                             key=lambda c: severity_order.get(severity_from_category(c), 4))

        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 🔧 FIX-IT LIST ({len(all_failures)} issues)")
        lines.append(f"")
        lines.append(f"Grouped by feature area, sorted by severity. Fix from top to bottom.")
        lines.append(f"")

        fix_num = 0
        for cat in sorted_cats:
            failures = by_category[cat]
            severity = severity_from_category(cat)
            lines.append(f"### {severity} {cat} ({len(failures)} failures)")
            lines.append(f"")

            for f in failures:
                fix_num += 1
                lines.append(f"#### Fix #{fix_num}: `{f['test']}`")
                lines.append(f"- **Source:** {f['source']} test")
                if f["message"]:
                    lines.append(f"- **Error:** `{f['message']}`")
                if f["file"]:
                    lines.append(f"- **Location:** `{f['file']}:{f['lineno']}`")
                if f["traceback"]:
                    # Truncate long tracebacks
                    tb = f["traceback"]
                    if len(tb) > 800:
                        tb = tb[:800] + "\n... (truncated)"
                    lines.append(f"- **Details:**")
                    lines.append(f"```")
                    lines.append(tb)
                    lines.append(f"```")
                lines.append(f"- **Status:** [ ] Not started")
                lines.append(f"")

    else:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 🔧 FIX-IT LIST")
        lines.append(f"")
        lines.append(f"🎉 **No issues found!** All tests passed.")
        lines.append(f"")

    # ---- DETAILED RESULTS: API TESTS ----
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Detailed Results: Backend API Tests")
    lines.append(f"")
    lines.append(f"**{pytest_results['summary']}** ({pytest_results['duration']}s)")
    lines.append(f"")

    if pytest_results["passed"]:
        lines.append(f"<details>")
        lines.append(f"<summary>✅ Passed ({len(pytest_results['passed'])})</summary>")
        lines.append(f"")
        for t in pytest_results["passed"]:
            lines.append(f"- `{t['nodeid']}` ({t['duration']}s)")
        lines.append(f"")
        lines.append(f"</details>")
        lines.append(f"")

    if pytest_results["failed"]:
        lines.append(f"### ❌ Failed ({len(pytest_results['failed'])})")
        lines.append(f"")
        for t in pytest_results["failed"]:
            lines.append(f"- **`{t['nodeid']}`** ({t['duration']}s)")
            if t.get("message"):
                lines.append(f"  - {t['message']}")
        lines.append(f"")

    if pytest_results["errors"]:
        lines.append(f"### 💥 Errors ({len(pytest_results['errors'])})")
        lines.append(f"")
        for t in pytest_results["errors"]:
            lines.append(f"- **`{t['nodeid']}`**")
            if t.get("message"):
                lines.append(f"  - {t['message']}")
        lines.append(f"")

    if pytest_results["skipped"]:
        lines.append(f"<details>")
        lines.append(f"<summary>⏭️ Skipped ({len(pytest_results['skipped'])})</summary>")
        lines.append(f"")
        for t in pytest_results["skipped"]:
            reason = t.get("reason", "")
            lines.append(f"- `{t['nodeid']}` {('— ' + reason) if reason else ''}")
        lines.append(f"")
        lines.append(f"</details>")
        lines.append(f"")

    # ---- DETAILED RESULTS: E2E TESTS ----
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Detailed Results: Frontend E2E Tests")
    lines.append(f"")
    lines.append(f"**{pw_results['summary']}** ({pw_results['duration']:.1f}s)")
    lines.append(f"")

    if pw_results["passed"]:
        lines.append(f"<details>")
        lines.append(f"<summary>✅ Passed ({len(pw_results['passed'])})</summary>")
        lines.append(f"")
        for t in pw_results["passed"]:
            lines.append(f"- `{t['name']}` ({t['duration']}s)")
        lines.append(f"")
        lines.append(f"</details>")
        lines.append(f"")

    if pw_results["failed"]:
        lines.append(f"### ❌ Failed ({len(pw_results['failed'])})")
        lines.append(f"")
        for t in pw_results["failed"]:
            lines.append(f"- **`{t['name']}`** ({t['duration']}s)")
            if t.get("message"):
                msg = t["message"][:300]
                lines.append(f"  - {msg}")
            if t.get("screenshots"):
                for ss in t["screenshots"]:
                    lines.append(f"  - 📸 Screenshot: `{ss}`")
        lines.append(f"")

    # ---- RAW LOG PATHS ----
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Raw Logs")
    lines.append(f"")
    lines.append(f"For full stack traces and verbose output:")
    lines.append(f"- pytest output: `{pytest_log_path}`")
    lines.append(f"- pytest JSON: `{pytest_log_path.replace('_output_', '_results_').replace('.txt', '.json')}`")
    lines.append(f"- E2E output: `{e2e_log_path}`")
    lines.append(f"- E2E JSON: `{e2e_log_path.replace('_output_', '_results_').replace('.txt', '.json')}`")
    lines.append(f"- Playwright HTML report: `G:\\Model_Mesh\\tests\\e2e\\playwright-report\\index.html`")
    lines.append(f"")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 7:
        print("Usage: generate_report.py <pytest_json> <e2e_json> <pytest_log> <e2e_log> <output_md> <timestamp>")
        sys.exit(1)

    pytest_json_path = sys.argv[1]
    e2e_json_path = sys.argv[2]
    pytest_log_path = sys.argv[3]
    e2e_log_path = sys.argv[4]
    output_path = sys.argv[5]
    timestamp = sys.argv[6]

    # Parse results
    pytest_data = load_json(pytest_json_path)
    e2e_data = load_json(e2e_json_path)

    pytest_results = parse_pytest_results(pytest_data)
    pw_results = parse_playwright_results(e2e_data)

    # Generate report
    report = generate_report(pytest_results, pw_results, pytest_log_path, e2e_log_path, timestamp)

    # Write report
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Report written to: {output_path}")

    # Also write a summary to console
    total_fail = len(pytest_results["failed"]) + len(pytest_results["errors"]) + len(pw_results["failed"])
    if total_fail > 0:
        print(f"\n⚠️  {total_fail} issue(s) found — see FIX-IT LIST in report")
    else:
        print(f"\n✅ All tests passed!")


if __name__ == "__main__":
    main()
