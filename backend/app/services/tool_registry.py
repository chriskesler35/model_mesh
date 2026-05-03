"""Canonical tool definitions for the DevForgeAI agent harness.

All agent backends — cloud (OpenAI, Anthropic, Google, OpenRouter) and local
(Ollama) — use the same tool set.  This module provides:

  1. OpenAI-format function schemas used with LiteLLM's ``tools=`` parameter
     for models that support native function calling.
  2. Capability detection — which providers/models support function calling.
  3. System-prompt fragments for models that do NOT support function calling
     (CMD: text-parsing fallback path).

The goal is that an Ollama/qwen2.5-coder agent and a GPT-4o agent receive
identical tool capabilities; only the transport format differs.
"""

from __future__ import annotations

from typing import Any

# ── Capability detection ──────────────────────────────────────────────────────

# Providers that always support function calling via their API.
FUNCTION_CALLING_PROVIDERS: frozenset[str] = frozenset(
    {
        "openai",
        "openai-codex",
        "anthropic",
        "google",
        "openrouter",
        "github-copilot",
    }
)

# Ollama model base-names (prefix match, case-insensitive, ignores :tag suffix)
# that support OpenAI-compatible function calling.  Keep this list current as
# new models are released with tool support.
OLLAMA_FUNCTION_CALLING_MODELS: frozenset[str] = frozenset(
    {
        "qwen2.5-coder",
        "qwen2.5",
        "qwen2",
        "qwen3",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "mistral",
        "mistral-nemo",
        "devstral",
        "command-r",
        "command-r-plus",
        "firefunction-v2",
        "hermes3",
        "nous-hermes2",
        "functionary",
        "nexusraven",
    }
)


def provider_supports_function_calling(
    provider_name: str, model_id: str = ""
) -> bool:
    """Return True if this provider+model combo supports native function calling.

    For Ollama, checks the model base name against a known-good list.
    For all major cloud providers, always returns True.
    """
    pname = (provider_name or "").lower().strip()
    if pname in FUNCTION_CALLING_PROVIDERS:
        return True
    if pname == "ollama":
        # Strip version tag: "qwen2.5-coder:32b" → "qwen2.5-coder"
        model_base = (model_id or "").lower().split(":")[0]
        return any(
            model_base.startswith(known)
            for known in OLLAMA_FUNCTION_CALLING_MODELS
        )
    return False


# ── Tool schemas (OpenAI function-calling format) ─────────────────────────────

_READ_FILE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read the contents of a file in the project workspace. "
            "Returns the file text, optionally limited to a line range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the workspace root.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "1-based line number to start reading from (optional).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "1-based line number to stop reading at (optional).",
                },
            },
            "required": ["path"],
        },
    },
}

_READ_LOCAL_FILE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "read_local_file",
        "description": (
            "Reads the contents of a local file on the host machine. "
            "Use this to inspect configuration files outside the workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": (
                        "Absolute path to the file, e.g. "
                        "C:\\Users\\chris\\.openclaw\\config.json"
                    ),
                },
            },
            "required": ["filepath"],
        },
    },
}

_WRITE_FILE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": (
            "Write or overwrite a file in the project workspace with the given content. "
            "Creates parent directories automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the workspace root.",
                },
                "content": {
                    "type": "string",
                    "description": "The complete content to write to the file.",
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Create parent directories if they do not exist. Default true.",
                },
            },
            "required": ["path", "content"],
        },
    },
}

_LIST_DIR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_dir",
        "description": "List files and directories at the given path in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to list. Use '.' for workspace root.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Recursively list all nested files. Default false.",
                },
            },
            "required": ["path"],
        },
    },
}

_RUN_SHELL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": (
            "Execute a shell command in a target directory. "
            "Use for running tests, builds, git operations, and other system commands. "
            "Destructive commands require user approval per the safety policy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum seconds to allow the command to run. Default 60.",
                },
                "working_directory": {
                    "type": "string",
                    "description": (
                        "Optional working directory. Can be absolute (including other drives, "
                        "e.g. C:\\Projects\\myapp) or relative to the workspace root."
                    ),
                },
            },
            "required": ["command"],
        },
    },
}

_INSTALL_PACKAGE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "install_package",
        "description": (
            "Install one or more packages using pip, npm, yarn, pnpm, cargo, or go. "
            "Example: packages='requests httpx', manager='pip'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "string",
                    "description": "Space-separated list of package names to install.",
                },
                "manager": {
                    "type": "string",
                    "enum": ["pip", "npm", "yarn", "pnpm", "cargo", "go"],
                    "description": "Package manager to use. Default 'pip'.",
                },
                "working_directory": {
                    "type": "string",
                    "description": (
                        "Optional directory where install command should run. Can be absolute "
                        "(cross-drive) or relative to workspace root."
                    ),
                },
            },
            "required": ["packages"],
        },
    },
}

_WEB_FETCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": (
            "Fetch the content of a URL and return the response body. "
            "Useful for reading API docs, downloading data, or checking endpoints."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch.",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "description": "HTTP method. Default 'GET'.",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional dict of HTTP request headers.",
                },
                "body": {
                    "type": "string",
                    "description": "Request body for POST requests.",
                },
            },
            "required": ["url"],
        },
    },
}

# ── Registry ──────────────────────────────────────────────────────────────────

# Ordered list of all available tools — this is the default set given to agents.
ALL_TOOLS: list[str] = [
    "read_file",
    "read_local_file",
    "write_file",
    "list_dir",
    "run_shell",
    "install_package",
    "web_fetch",
]

# Map of tool name → OpenAI schema
ALL_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": _READ_FILE_SCHEMA,
    "read_local_file": _READ_LOCAL_FILE_SCHEMA,
    "write_file": _WRITE_FILE_SCHEMA,
    "list_dir": _LIST_DIR_SCHEMA,
    "run_shell": _RUN_SHELL_SCHEMA,
    "install_package": _INSTALL_PACKAGE_SCHEMA,
    "web_fetch": _WEB_FETCH_SCHEMA,
}

# How each tool is described in the system prompt for text-fallback models
_TOOL_PROMPT_LINES: dict[str, str] = {
    "read_file": "READ_FILE: <relative_path> [start_line] [end_line]  — read file contents",
    "read_local_file": "READ_LOCAL_FILE: <absolute_path>  — read local host file contents",
    "write_file": "WRITE_FILE: <relative_path>\n<content lines>\nEND_WRITE  — write/overwrite a file",
    "list_dir": "LIST_DIR: <relative_path> [recursive]  — list directory",
    "run_shell": "CMD: <command> [working_directory]  — run a shell command",
    "install_package": "INSTALL: <manager> <packages> [working_directory]  — install packages",
    "web_fetch": "FETCH: <url>  — fetch URL content",
}


def get_tool_schemas(tool_names: list[str]) -> list[dict[str, Any]]:
    """Return OpenAI function schemas for the given tool names.

    Unknown names are skipped silently for backward compatibility.
    """
    return [ALL_TOOL_SCHEMAS[name] for name in tool_names if name in ALL_TOOL_SCHEMAS]


def get_tool_prompt_fragment(tool_names: list[str]) -> str:
    """Return a system-prompt section describing available tools for text-based models.

    Used as the fallback when the model does not support native function calling.
    """
    if not tool_names:
        return ""

    lines = [
        "You have access to the following tools. Emit them on their own line(s):",
        "",
    ]
    for name in tool_names:
        if name in _TOOL_PROMPT_LINES:
            lines.append(f"  {_TOOL_PROMPT_LINES[name]}")
    lines += [
        "",
        "You may emit multiple tool calls per response.",
        "When the task is fully complete, output:  DONE: <final answer>",
    ]
    return "\n".join(lines)


def resolve_agent_tools(agent_tools_field) -> list[str]:
    """Normalise the agent.tools value into a list of canonical tool names.

    agent.tools may be stored as:
    - None / empty  → return ALL_TOOLS (full access by default)
    - list[str]     → filter against ALL_TOOL_SCHEMAS, return known names
    - JSON string   → parse then filter
    """
    import json

    if not agent_tools_field:
        return list(ALL_TOOLS)

    if isinstance(agent_tools_field, str):
        try:
            parsed = json.loads(agent_tools_field)
        except (ValueError, TypeError):
            # Treat as a single tool name or comma-separated
            parsed = [t.strip() for t in agent_tools_field.split(",") if t.strip()]
    else:
        parsed = list(agent_tools_field)

    known = [t for t in parsed if t in ALL_TOOL_SCHEMAS]
    # Backward compatibility: agents configured with read_file should
    # automatically receive read_local_file as well.
    if "read_file" in known and "read_local_file" not in known:
        known.append("read_local_file")
    return known if known else list(ALL_TOOLS)
