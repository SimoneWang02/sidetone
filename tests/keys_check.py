"""Manual check from WSL that a held talk key is kept from other programs: python3 tests/keys_check.py

Starts an overlay of its own with the talk key on F20 (a key no keyboard has and no program
uses, pressed here by Windows itself, with no Ctrl or Alt, so nothing the user is doing is
touched). Then it presses F20, repeats it the way a held key repeats, and lets go, while a
second program watches which of those presses the overlay passes on. (It watches before
Windows matches hotkeys, so it shows what the overlay itself holds back, which is what counts
once Ctrl or Alt has been let go and the hotkey no longer matches.)

Expected: only the first press and the release are passed on ("down up"), the overlay reports
the hold ("talk", then "talk_end"), the key is not left stuck, and the press after the hold is
passed on again in full.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, f"{ROOT}/hub")
import overlay  # noqa: E402

REPEATS = 4


def win(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()


command = overlay.command(f"{ROOT}/overlay/overlay.ps1", lambda line: print(" ", line))
print("  starting", os.path.basename(command[0]))
proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd="/mnt/c/Windows")
replies = queue.Queue()
threading.Thread(target=lambda: [replies.put(line.decode(errors="replace").strip()) for line in proc.stdout], daemon=True).start()


def send(**message):
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def drain(seconds):
    got, end = [], time.time() + seconds
    while time.time() < end:
        try:
            got.append(json.loads(replies.get(timeout=0.1)))
        except (queue.Empty, ValueError):
            pass
    return got


def wait_ready(timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if json.loads(replies.get(timeout=0.2)).get("type") == "ready":
                return True
        except (queue.Empty, ValueError):
            pass
    return False


ok = False
try:
    if not wait_ready():
        sys.exit("  !! the overlay did not start")
    send(type="config", opaque=True, still=True, mode="dots", focus_wheel="", hotkeys={"talk": "F20"},
         monitor=0, corner="bottom-right", offset_x=420, offset_y=260)
    for m in drain(1.5):
        if m.get("type") == "error":
            print("  overlay error:", m.get("message"))
    watcher = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win(f"{ROOT}/tests/keys_check.ps1"),
         "-Repeats", str(REPEATS)], capture_output=True, text=True, cwd="/mnt/c/Windows", timeout=60)
    seen, _, state = watcher.stdout.strip().partition(" | ")
    hotkeys = [m.get("name") for m in drain(1.0) if m.get("type") == "hotkey"]
    print("  the overlay passed on:", seen or "(nothing)", watcher.stderr.strip()[:300])
    print("  the overlay reported:", " ".join(hotkeys) or "(nothing)")
    print("  the key afterwards:", state)
    leaked = seen.split()[: -2].count("down") - 1  # all but the press after the hold, less the first press
    ok = seen == "down up down up" and hotkeys[:2] == ["talk", "talk_end"] and state == "released"
    print("  OK: the repeats of the held key were held back" if ok
          else f"  !! {max(leaked, 0)} of {REPEATS} repeats of the held key were passed on" if leaked > 0
          else "  !! not as expected")
finally:
    try:
        proc.stdin.close()
        proc.wait(5)
    except Exception:
        proc.kill()
sys.exit(0 if ok else 1)
