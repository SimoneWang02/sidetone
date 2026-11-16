"""What Claude Code itself records about its live sessions (~/.claude/sessions/<pid>.json).

Hooks do not report everything: pressing Esc sends no event, and a killed terminal sends no
SessionEnd. These files fill that gap. They are undocumented, so this is best effort: anything
missing or unreadable simply means "no extra knowledge".
"""
from __future__ import annotations

import json
import os


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def read(directory: str) -> dict[str, dict]:
    """session id -> {"status": "busy" | "idle", "status_at": epoch seconds} for running sessions."""
    found: dict[str, dict] = {}
    try:
        names = os.listdir(directory)
    except OSError:
        return found
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name)) as f:
                data = json.load(f)
            sid, pid = data["sessionId"], data["pid"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(sid, str) and isinstance(pid, int) and alive(pid):
            found[sid] = {"status": data.get("status"), "status_at": (data.get("statusUpdatedAt") or 0) / 1000}
    return found
