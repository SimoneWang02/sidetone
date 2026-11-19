"""Is the running hub older than its code on disk?

A fix only counts once the hub was restarted: on 2026-11-17 a reply was cut by a fault that had
been mended and committed two minutes earlier, because the hub was still running the old code.
`sidetone status` says so with this.
"""
from __future__ import annotations

import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def prints(folder: str = HERE, endings: tuple = (".py",)) -> dict:
    """What each source file in `folder` holds, as a fingerprint. Not its time of change: a file
    that was only touched, or rewritten with the same text by a checkout, has not changed."""
    found = {}
    try:
        for name in os.listdir(folder):
            if name.endswith(endings):
                with open(os.path.join(folder, name), "rb") as f:
                    found[name] = hashlib.sha1(f.read()).hexdigest()
    except OSError:
        pass
    return found


LOADED = prints()  # taken when the hub starts, which is when it reads its code


def changed(loaded: dict | None = None, folder: str = HERE, endings: tuple = (".py",)) -> list:
    """The files that are not as they were then: edited, added or removed."""
    loaded, now = LOADED if loaded is None else loaded, prints(folder, endings)
    return sorted(name for name in set(loaded) | set(now) if loaded.get(name) != now.get(name))
