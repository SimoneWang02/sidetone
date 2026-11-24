"""Processes the same way on every system: is one still running, and ending one with all it
started. Linux and the Mac have process groups and signal 0; Windows has neither (there,
os.kill(pid, 0) would send Ctrl+C), so it is asked through its own calls and taskkill.
"""
from __future__ import annotations

import os
import signal
import subprocess

WINDOWS = os.name == "nt"


def alive(pid: int) -> bool:
    if WINDOWS:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.GetLastError() == 5  # access denied: it is there, just not ours to ask
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def end_tree(proc: subprocess.Popen, hard: bool = True) -> None:
    """End a process started with start_new_session=True, and whatever it started."""
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/PID", str(proc.pid)] + (["/F"] if hard else []),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass
