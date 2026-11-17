"""Is the running hub older than its code on disk?

A fix only counts once the hub was restarted: on 2026-11-17 a reply was cut by a fault that had
been mended and committed two minutes earlier, because the hub was still running the old code.
`claude-speaks status` says so with this.
"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))


def times(folder: str = HERE, endings: tuple = (".py",)) -> dict:
    """When each source file in `folder` was last changed."""
    found = {}
    try:
        for name in os.listdir(folder):
            if name.endswith(endings):
                found[name] = os.path.getmtime(os.path.join(folder, name))
    except OSError:
        pass
    return found


LOADED = times()  # taken when the hub starts, which is when it reads its code


def changed(loaded: dict | None = None, folder: str = HERE, endings: tuple = (".py",)) -> list:
    """The files that are not as they were then: edited, added or removed."""
    loaded, now = LOADED if loaded is None else loaded, times(folder, endings)
    return sorted(name for name in set(loaded) | set(now) if loaded.get(name) != now.get(name))
