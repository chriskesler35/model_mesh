"""Command classifier — decides which tier a shell command belongs to.

Tier 1 (AUTO): read-only + clearly safe commands. Run without fanfare.
Tier 2 (NOTICE): install/write ops. Run auto, but with a visible banner.
Tier 3 (APPROVAL): destructive or network-leaking. Always requires
    user approval (even in pipeline auto-approve mode), UNLESS bypass
    mode is on — then user accepted the risk.

Classification is pattern-based. When nothing matches, default is TIER 3
(safest). User can extend the allowlist via a project-level trusted
commands file.
"""

from __future__ import annotations

import re
import shlex
from enum import Enum
from pathlib import Path
from typing import Optional


class CommandTier(str, Enum):
    AUTO = "auto"           # Tier 1: run silently
    NOTICE = "notice"       # Tier 2: run with banner
    APPROVAL = "approval"   # Tier 3: pause for user
    BLOCKED = "blocked"     # Sandbox restricted mode — never runs


# ─── Tier 1: AUTO — read-only, safe ────────────────────────────────────────────
# Each entry is a regex matched against the full command (with args).
_TIER1_PATTERNS = [
    # Filesystem read-only
    r"^ls(\s|$)", r"^dir(\s|$)", r"^pwd(\s|$)", r"^cat\s", r"^head\s", r"^tail\s",
    r"^grep\s", r"^rg\s", r"^find\s", r"^tree(\s|$)", r"^wc\s", r"^file\s",
    r"^which\s", r"^where\s", r"^type\s", r"^whoami(\s|$)", r"^date(\s|$)",
    # Git read-only
    r"^git\s+(status|log|diff|show|branch(\s|$)|blame|stash\s+list|config\s+--get|remote(\s+-v|\s+show)?)",
    # Tests
    r"^pytest(\s|$)", r"^jest(\s|$)", r"^vitest(\s|$)", r"^mocha(\s|$)",
    r"^npm\s+test(\s|$)", r"^npm\s+run\s+test", r"^yarn\s+test(\s|$)", r"^pnpm\s+test(\s|$)",
    r"^cargo\s+test(\s|$)", r"^cargo\s+check(\s|$)", r"^cargo\s+clippy(\s|$)",
    r"^go\s+test(\s|$)", r"^go\s+vet(\s|$)", r"^go\s+build(\s|$)",
    r"^mvn\s+test(\s|$)", r"^gradle\s+test(\s|$)",
    # Build/dev (non-install)
    r"^npm\s+run\s+(build|dev|start|serve|lint|format|typecheck)",
    r"^yarn\s+(build|dev|start|serve|lint|format)",
    r"^pnpm\s+(build|dev|start|serve|lint|format)",
    r"^tsc(\s|$)", r"^eslint\s", r"^prettier\s", r"^ruff\s", r"^black\s", r"^mypy\s",
    # Python exec
    r"^python\s+-m\s", r"^python\s+-c\s", r"^python\s+[\w\./_-]+\.py",
    r"^python3\s+-m\s", r"^python3\s+-c\s", r"^python3\s+[\w\./_-]+\.py",
    r"^node\s+[\w\./_-]+\.js", r"^node\s+--version",
    # Curl / http to localhost only
    r"^curl\s+.*(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|/|\s|$)",
    # Version checks
    r".*--version(\s|$)", r".*-v(\s|$)",
    # Environment introspection
    r"^env(\s|$)", r"^printenv(\s|$)", r"^set(\s|$)",
    # Help
    r".*--help(\s|$)", r".*-h(\s|$)",
]

# ─── Tier 2: NOTICE — install/write operations ────────────────────────────────
_TIER2_PATTERNS = [
    # Package installers
    r"^npm\s+(install|i|ci|update|outdated|audit)(\s|$)",
    r"^yarn\s+(install|add|upgrade|why|outdated)(\s|$)",
    r"^pnpm\s+(install|add|update|audit)(\s|$)",
    r"^pip\s+(install|uninstall)(\s|$)",
    r"^pip3\s+(install|uninstall)(\s|$)",
    r"^uv\s+(pip\s+install|add|sync|lock)(\s|$)",
    r"^poetry\s+(add|install|update|remove|lock)(\s|$)",
    r"^cargo\s+(add|build|update|install)(\s|$)",
    r"^go\s+(get|mod\s+(tidy|download|vendor))(\s|$)",
    # Git write ops (LOCAL only — push is Tier 3)
    r"^git\s+(add|commit|checkout\s+-b|switch(\s+-c)?|tag(\s|$)|stash(\s+(save|push|pop|apply))?|restore|mv)(\s|$)",
    r"^git\s+init(\s|$)", r"^git\s+clone\s",
    r"^git\s+fetch(\s|$)", r"^git\s+pull(\s|$)", r"^git\s+merge\s",
    r"^git\s+rebase(?!\s+--(hard|abort))",  # rebase but not --hard/abort
    # File-system create (safe)
    r"^mkdir(\s|$)", r"^touch\s", r"^cp\s(?!.*-r\s+/|.*-rf\s+/)",
    # Build artifacts
    r"^make(\s|$)", r"^cmake(\s|$)", r"^cargo\s+run(\s|$)", r"^go\s+run(\s|$)",
    # docker build only (not rm/prune)
    r"^docker\s+(build|compose\s+up|compose\s+build)(\s|$)",
    # curl GET to non-localhost
    r"^curl\s+(?!-X\s+(POST|PUT|DELETE|PATCH))",
]

# ─── Tier 3: APPROVAL — destructive or network-leaking ────────────────────────
_TIER3_PATTERNS = [
    # Git write-to-remote (the big one — affects github/gitlab)
    r"^git\s+push(\s|$)", r"^git\s+push\s+--force", r"^git\s+push\s+-f(\s|$)",
    r"^git\s+reset\s+--hard", r"^git\s+clean\s+-[fFdxX]",
    r"^git\s+rebase\s+--hard", r"^git\s+branch\s+-D",
    r"^git\s+tag\s+-d", r"^git\s+push.*--delete",
    # Destructive filesystem
    r"^rm(\s|$)", r"^del(\s|$)", r"^rmdir\s+/s", r"^rd\s+/s",
    # Destructive shutil on network or system dirs
    r"^mv\s+", r"^cp\s+-r?f?\s+.*/(etc|bin|sbin|usr|var|windows|system32)",
    # Privilege escalation
    r"^sudo(\s|$)", r"^su(\s|$)", r"^runas(\s|$)",
    r"^chmod\s+\+x", r"^chown\s", r"^chgrp\s", r"^setcap\s",
    # Process killing
    r"^kill(\s|$)", r"^pkill(\s|$)", r"^killall(\s|$)", r"^taskkill(\s|$)",
    # Docker destructive
    r"^docker\s+(rm|rmi|prune|system\s+prune|volume\s+rm|network\s+rm)(\s|$)",
    r"^docker\s+compose\s+down\s+-v",
    # Outbound network (non-GET or non-localhost)
    r"^curl\s+-X\s+(POST|PUT|DELETE|PATCH)",
    r"^wget\s", r"^ssh\s", r"^scp\s", r"^rsync\s", r"^sftp\s",
    # Package manager removal
    r"^npm\s+uninstall(\s|$)", r"^pip\s+uninstall(\s|$)",
    r"^apt(-get)?\s+(install|remove|purge|upgrade)",
    r"^yum\s+(install|remove)", r"^dnf\s+(install|remove)",
    r"^brew\s+(install|uninstall|upgrade)", r"^choco\s+(install|uninstall)",
    r"^winget\s+(install|uninstall|upgrade)",
    # Output redirect to system dirs
    r">\s*(/etc/|/bin/|/sbin/|/usr/|/var/|C:\\Windows\\|C:\\Program Files)",
]


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_T1 = _compile(_TIER1_PATTERNS)
_T2 = _compile(_TIER2_PATTERNS)
_T3 = _compile(_TIER3_PATTERNS)


def classify_command(
    command: str,
    sandbox_mode: str = "full",
    extra_trusted_patterns: Optional[list[str]] = None,
) -> CommandTier:
    """Classify a shell command into a safety tier.

    Args:
        command: the full command line as a string
        sandbox_mode: "restricted" blocks everything; "full" classifies normally
        extra_trusted_patterns: project-local trusted patterns (promote to Tier 1)

    Returns:
        CommandTier enum
    """
    cmd = (command or "").strip()
    if not cmd:
        return CommandTier.APPROVAL

    # Restricted sandbox: block ALL shell commands
    if sandbox_mode == "restricted":
        return CommandTier.BLOCKED

    # Project-local trusted patterns take priority (promote to Tier 1)
    if extra_trusted_patterns:
        for pattern in extra_trusted_patterns:
            try:
                if re.match(pattern, cmd, re.IGNORECASE):
                    return CommandTier.AUTO
            except re.error:
                continue

    # Tier 3 wins first — safety over convenience.
    # If a command matches both a Tier 1/2 and a Tier 3 pattern, treat as Tier 3.
    for p in _T3:
        if p.search(cmd):
            return CommandTier.APPROVAL

    for p in _T1:
        if p.match(cmd):
            return CommandTier.AUTO

    for p in _T2:
        if p.match(cmd):
            return CommandTier.NOTICE

    # Unknown commands default to APPROVAL (safest)
    return CommandTier.APPROVAL


def describe_tier(tier: CommandTier) -> str:
    """Human-friendly description of a tier for UI display."""
    return {
        CommandTier.AUTO: "Safe — will run automatically",
        CommandTier.NOTICE: "Modifies your environment — will run with a notice",
        CommandTier.APPROVAL: "Destructive or external — needs your approval",
        CommandTier.BLOCKED: "Blocked by sandbox policy",
    }[tier]


def load_project_trusted_patterns(project_path: str | Path | None) -> list[str]:
    """Load project-local extra allowlist from .devforgeai/trusted_commands.txt.

    Each non-empty, non-comment line is treated as a regex.
    """
    if not project_path:
        return []
    try:
        path = Path(project_path) / ".devforgeai" / "trusted_commands.txt"
        if not path.exists():
            return []
        patterns = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
        return patterns
    except Exception:
        return []
