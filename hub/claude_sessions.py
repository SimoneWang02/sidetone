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
    """session id -> {"pid", "status": "busy" | "idle", "status_at": epoch seconds, "name": its title} for running sessions."""
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
            name = data.get("name")
            if not isinstance(name, str) or data.get("nameSource") == "derived":
                name = ""  # "derived" is a placeholder made at start: the folder plus two letters ("my-project-3f")
            found[sid] = {"pid": pid, "status": data.get("status"), "status_at": at / 1000 if isinstance(at := data.get("statusUpdatedAt"), (int, float)) else 0,
                          "name": name}
    return found


def tool_shells(pid: int) -> dict[int, str]:
    """The commands a session's Bash tool is running right now: process id -> command line.

    Claude Code runs each one in a shell of its own, a child of the session, which first reads
    the session's shell snapshot (`~/.claude/shell-snapshots/...`); that is how they are told
    from the session's other children, the hooks. Linux only (it reads /proc), and as
    undocumented as the session files: where it cannot be read, nothing is found.
    """
    found: dict[int, str] = {}
    try:
        threads = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return found
    for thread in threads:
        try:
            with open(f"/proc/{pid}/task/{thread}/children") as f:
                children = f.read().split()
        except OSError:
            continue
        for child in children:
            try:
                with open(f"/proc/{child}/cmdline", "rb") as f:
                    line = f.read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if "/shell-snapshots/" in line:
                found[int(child)] = line
    return found
