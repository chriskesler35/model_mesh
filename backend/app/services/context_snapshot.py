"""
Context Snapshot Service

Automatically writes dated session snapshots after every exchange so that
broken sessions, restarts, or compactions can be recovered cleanly.

Also maintains a rolling MEMORY.md that accumulates long-term context
across all conversations.

Snapshot layout:
  data/context/
    MEMORY.md                          ← long-term rolling memory
    YYYY-MM-DD/
      session_{conv_id_short}_{HH-MM}.md   ← per-exchange snapshot
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_CONTEXT_DIR = _DATA_DIR / "context"
_MEMORY_FILE = _CONTEXT_DIR / "MEMORY.md"

# How many messages before we do a memory distillation pass
DISTILL_EVERY_N_MESSAGES = 10


def _today_dir() -> Path:
    """Return today's snapshot directory, creating it if needed."""
    d = _CONTEXT_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(conversation_id: str) -> Path:
    """Return the snapshot file path for this conversation at this moment."""
    short_id = conversation_id.replace("-", "")[:8]
    ts = datetime.now(timezone.utc).strftime("%H-%M")
    return _today_dir() / f"session_{short_id}_{ts}.md"


def _latest_snapshot(conversation_id: str) -> Path | None:
    """
    Find the most recent snapshot for a conversation across all date dirs.
    Returns None if none found.
    """
    short_id = conversation_id.replace("-", "")[:8]
    pattern = f"session_{short_id}_*.md"
    candidates = sorted(_CONTEXT_DIR.rglob(pattern), reverse=True)
    return candidates[0] if candidates else None


def write_snapshot(
    conversation_id: str,
    title: str,
    messages: list[dict],   # [{"role": "user"|"assistant", "content": "..."}]
    persona_name: str = "",
    model_name: str = "",
) -> Path:
    """
    Write a full session snapshot to disk after an exchange.
    Called from _save_messages in chat.py.
    """
    _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = _snapshot_path(conversation_id)

    # Build human-readable snapshot
    lines = [
        f"# Session Snapshot",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Conversation ID | `{conversation_id}` |",
        f"| Title | {title or 'Untitled'} |",
        f"| Persona | {persona_name or '—'} |",
        f"| Model | {model_name or '—'} |",
        f"| Snapshot time | {now.strftime('%Y-%m-%d %H:%M:%S UTC')} |",
        f"| Message count | {len(messages)} |",
        f"",
        f"## Conversation",
        f"",
    ]

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        icon = "🧑" if role == "user" else "🤖"
        lines.append(f"### {icon} {role.title()}")
        lines.append(f"")
        lines.append(content)
        lines.append(f"")

    # Extract last exchange for quick-glance summary at top
    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    last_asst = next((m["content"] for m in reversed(messages) if m.get("role") == "assistant"), "")

    summary = [
        f"## Last Exchange",
        f"",
        f"**User:** {last_user[:300]}{'...' if len(last_user) > 300 else ''}",
        f"",
        f"**Assistant:** {last_asst[:300]}{'...' if len(last_asst) > 300 else ''}",
        f"",
        f"---",
        f"",
    ]

    content_str = "\n".join(summary + lines)
    path.write_text(content_str, encoding="utf-8")
    logger.debug(f"Snapshot written: {path}")
    return path


def read_snapshot(conversation_id: str) -> dict | None:
    """
    Read the latest snapshot for a conversation.
    Returns dict with path, content, and parsed metadata, or None.
    """
    path = _latest_snapshot(conversation_id)
    if not path or not path.exists():
        return None

    content = path.read_text(encoding="utf-8")

    # Parse the metadata table
    meta = {"path": str(path), "raw": content}
    for line in content.splitlines():
        if "| Conversation ID |" in line:
            meta["conversation_id"] = line.split("`")[1] if "`" in line else conversation_id
        elif "| Title |" in line:
            meta["title"] = line.split("|")[2].strip()
        elif "| Persona |" in line:
            meta["persona"] = line.split("|")[2].strip()
        elif "| Model |" in line:
            meta["model"] = line.split("|")[2].strip()
        elif "| Snapshot time |" in line:
            meta["snapshot_time"] = line.split("|")[2].strip()
        elif "| Message count |" in line:
            try:
                meta["message_count"] = int(line.split("|")[2].strip())
            except ValueError:
                pass

    return meta


def list_recent_snapshots(days: int = 7) -> list[dict]:
    """List all snapshots from the last N days, newest first."""
    if not _CONTEXT_DIR.exists():
        return []

    snapshots = []
    for md_file in sorted(_CONTEXT_DIR.rglob("session_*.md"), reverse=True):
        # Only include from last N days
        try:
            date_part = md_file.parent.name  # YYYY-MM-DD
            file_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - file_date).days
            if age_days > days:
                continue
        except ValueError:
            continue

        snapshots.append({
            "path": str(md_file),
            "date": date_part,
            "filename": md_file.name,
            "size_bytes": md_file.stat().st_size,
        })

    return snapshots


def update_memory(new_facts: str, source: str = "conversation") -> None:
    """
    Append distilled facts to the rolling MEMORY.md file.
    new_facts should be a concise bullet-point summary.
    """
    _CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n## {now} (via {source})\n\n{new_facts.strip()}\n"

    if _MEMORY_FILE.exists():
        existing = _MEMORY_FILE.read_text(encoding="utf-8")
    else:
        existing = "# MEMORY.md — Long-Term Context\n\nThis file accumulates important context across all sessions.\n"

    _MEMORY_FILE.write_text(existing + entry, encoding="utf-8")
    logger.info(f"MEMORY.md updated ({len(new_facts)} chars)")


def read_memory() -> str:
    """Read the current MEMORY.md content."""
    if _MEMORY_FILE.exists():
        return _MEMORY_FILE.read_text(encoding="utf-8")
    return ""


async def maybe_distill_memory(
    conversation_id: str,
    messages: list[dict],
    model_name: str,
    message_count: int,
) -> bool:
    """
    If we've hit the distillation threshold, call the AI to summarize
    what's been learned and append it to MEMORY.md.
    Returns True if distillation ran.
    """
    if message_count % DISTILL_EVERY_N_MESSAGES != 0:
        return False

    try:
        from app.config import settings
        import httpx

        # Build a concise recent-exchange context (last 10 messages)
        recent = messages[-10:]
        convo_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:400]}" for m in recent
        )

        distill_prompt = (
            "You are a memory distillation assistant. "
            "Given the following recent conversation, extract 3-7 key facts, "
            "decisions, preferences, or topics that are worth remembering long-term. "
            "Format as concise bullet points. Be specific, not generic.\n\n"
            f"CONVERSATION:\n{convo_text}\n\n"
            "KEY FACTS TO REMEMBER:"
        )

        # Use litellm directly to avoid circular imports
        import litellm
        resp = await litellm.acompletion(
            model=model_name or "ollama/llama3.1:8b",
            messages=[{"role": "user", "content": distill_prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        facts = resp.choices[0].message.content.strip()
        if facts:
            update_memory(facts, source=f"conv:{conversation_id[:8]}")
            return True

    except Exception as e:
        logger.warning(f"Memory distillation skipped: {e}")

    return False
