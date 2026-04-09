"""Mention parsing utilities for @username detection in chat messages."""

import re
from typing import List


# Matches @username patterns (alphanumeric + underscores + hyphens)
_MENTION_RE = re.compile(r"@(\w[\w\-]*)")


def extract_mentions(text: str) -> List[str]:
    """Extract unique @usernames from message text.

    Returns a list of unique usernames (without the @ prefix).
    """
    if not text:
        return []
    return list(dict.fromkeys(_MENTION_RE.findall(text)))
