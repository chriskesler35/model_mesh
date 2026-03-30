"""
SandboxGuard — path restriction and tool allowlist enforcement.

Two modes per project:
  restricted  — agent confined to project root; shell_execute blocked;
                no reads/writes outside the project directory
  full        — unrestricted; agent has full system access

Usage:
    guard = SandboxGuard(project_root="/path/to/project", mode="restricted")
    guard.check_path("/path/to/project/src/main.py")  # OK
    guard.check_path("/etc/passwd")                    # raises SandboxViolation
    guard.check_tool("read_file")                      # OK
    guard.check_tool("shell_execute")                  # raises SandboxViolation
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxViolation(Exception):
    """Raised when an operation violates sandbox policy."""
    def __init__(self, message: str, operation: str = "", path: str = ""):
        super().__init__(message)
        self.operation = operation
        self.path = path


# Tools blocked in restricted mode
RESTRICTED_TOOLS = {
    "shell_execute",    # arbitrary shell commands — full system access
    "http_request",     # outbound network (optional — comment out if you want web access)
}

# Tools always allowed in any mode
ALWAYS_ALLOWED_TOOLS = {
    "read_file",
    "write_file",
    "run_tests",
    "git_commit",
    "web_search",
    "generate_image",
    "image_variation",
}


class SandboxGuard:
    """Enforces path and tool restrictions for a project."""

    def __init__(self, project_root: str | Path, mode: str = "restricted"):
        self.mode = mode
        self.root = Path(project_root).resolve() if project_root else None

    @property
    def is_restricted(self) -> bool:
        return self.mode == "restricted"

    def check_path(self, path: str | Path) -> Path:
        """
        Validate a file path.
        In restricted mode, raises SandboxViolation if path escapes project root.
        Returns the resolved Path if OK.
        """
        if not self.is_restricted or self.root is None:
            return Path(path).resolve()

        resolved = Path(path).resolve()

        # Allow relative paths that stay within root
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise SandboxViolation(
                f"Path '{path}' is outside the project directory '{self.root}'. "
                f"This project is in restricted mode.",
                operation="file_access",
                path=str(path),
            )

        return resolved

    def check_tool(self, tool_name: str) -> None:
        """
        Validate a tool call.
        In restricted mode, raises SandboxViolation for blocked tools.
        """
        if not self.is_restricted:
            return

        if tool_name in RESTRICTED_TOOLS:
            raise SandboxViolation(
                f"Tool '{tool_name}' is not allowed in restricted mode. "
                f"Switch the project to full access mode to use this tool.",
                operation="tool_call",
                path=tool_name,
            )

    def check_command(self, command: str) -> None:
        """
        Validate a shell command in restricted mode.
        Always blocked in restricted mode regardless of content.
        """
        if not self.is_restricted:
            return

        raise SandboxViolation(
            f"Shell commands are blocked in restricted mode. "
            f"Switch to full access mode to run: {command[:80]}",
            operation="shell_execute",
            path=command,
        )

    def validate_write(self, path: str | Path, content: str = "") -> Path:
        """Validate a file write operation — checks path and content length."""
        resolved = self.check_path(path)

        # Warn on large writes (agent writing huge files)
        if len(content) > 1_000_000:  # 1MB
            logger.warning(f"Large write detected: {len(content)} bytes to {resolved}")

        return resolved

    def summary(self) -> dict:
        """Return a human-readable summary of the current sandbox policy."""
        if not self.is_restricted:
            return {
                "mode": "full",
                "label": "Full Access",
                "description": "Agent has unrestricted read/write/execute access to the entire system.",
                "blocked_tools": [],
                "path_restriction": None,
            }
        return {
            "mode": "restricted",
            "label": "Restricted",
            "description": f"Agent is confined to '{self.root}'. Shell commands and outbound requests are blocked.",
            "blocked_tools": list(RESTRICTED_TOOLS),
            "path_restriction": str(self.root),
        }


def get_guard(project: dict) -> SandboxGuard:
    """Create a SandboxGuard from a project dict."""
    return SandboxGuard(
        project_root=project.get("path", ""),
        mode=project.get("sandbox_mode", "restricted"),
    )
