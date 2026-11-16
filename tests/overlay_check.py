"""Manual check of the overlay window from WSL: python3 tests/overlay_check.py OUT_DIR

Starts the overlay by itself, feeds it made-up content, and saves a PNG of each view to OUT_DIR.
The window is drawn opaque and only its own rectangle is captured, so nothing else on the
screen ends up in the pictures. It uses spare hotkeys so it can run next to the live overlay.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
os.makedirs(out, exist_ok=True)


def win(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()


proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                         win(f"{ROOT}/overlay/overlay.ps1")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, cwd="/mnt/c/Windows")
replies = queue.Queue()
threading.Thread(target=lambda: [replies.put(line.decode(errors="replace").strip()) for line in proc.stdout], daemon=True).start()


def send(**message):
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def wait(kind, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            line = replies.get(timeout=0.2)
            message = json.loads(line)
        except (queue.Empty, ValueError):
            continue
        if message.get("type") == "error":
            print("  overlay error:", message.get("message"))
        if message.get("type") == kind:
            return message
    print(f"  !! no '{kind}' reply within {timeout}s")
    return None


def shot(name):
    time.sleep(0.5)
    send(type="bounds")
    b = wait("bounds", 5)
    if not b or not b.get("visible"):
        print(f"  {name}: not visible")
        return b
    script = (f"Add-Type -AssemblyName System.Drawing; $b = New-Object System.Drawing.Bitmap {b['w']},{b['h']}; "
              f"[System.Drawing.Graphics]::FromImage($b).CopyFromScreen({b['x']},{b['y']},0,0,$b.Size); $b.Save('{win(out)}\\{name}.png')")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], cwd="/mnt/c/Windows")
    print(f"  {name}.png  at {b['x']},{b['y']}  {b['w']}x{b['h']}  monitor {b.get('monitor')}  catches mouse: {b.get('catches_mouse')}")
    return b


SESSIONS = [
    dict(name="claude-speaks", state="done", text="Pushed, all up to date.", meta="", speaking=False),
    dict(name="api-server", state="working", text="Running tests", meta="\U0001F3A4 · 3/5 · 6m", speaking=True),
    dict(name="web-app", state="needs_you", text="asks: Which drink?", meta="", speaking=False),
    dict(name="data-pipeline", state="failed", text="error: rate limit", meta="", speaking=False),
    dict(name="notes", state="idle", text="", meta="", speaking=False),
]
HISTORY = [dict(ago="now", name="api-server", text="All forty two tests pass."),
           dict(ago="3m", name="web-app", text="The login page is fixed and ready for review."),
           dict(ago="12m", name="data-pipeline", text="I hit an error: rate limit")]
KEYS = {"toggle": "Ctrl+Alt+F9"}

if not wait("ready", 40):
    proc.kill()
    sys.exit(1)
send(type="config", opaque=True, mode="dots", hotkeys=KEYS)
send(type="state", sessions=SESSIONS, history=HISTORY)
shot("dots")
send(type="flash", state="done", name="api-server", text="All forty two tests pass.", seconds=2)
shot("flash")
time.sleep(2)
send(type="request", name="web-app", text="asks: Which drink?", detail="1  Tea   2  Coffee   3  Water",
     keys="Ctrl+Alt+1 to Ctrl+Alt+3 answers  ·  question 1 of 2")
shot("question")
send(type="request")
send(type="banner", text="→ web-app: “Also add a test for the empty input case.”", hint="tap Ctrl+Alt+Space to send  ·  Ctrl+Alt+Backspace cancels")
shot("follow-up")
send(type="banner")
send(type="mode", mode="list")
shot("list")
send(type="peek", on=True)
shot("list-history")
send(type="peek", on=False)
send(type="config", opaque=True, mode="dots", hotkeys=KEYS, monitor=1, corner="bottom-left", offset_x=30, offset_y=30)
shot("second-monitor")
send(type="move")
shot("move")
proc.stdin.close()
try:
    print("  exited with", proc.wait(5), "when its input closed")
except subprocess.TimeoutExpired:
    print("  !! did not exit when its input closed")
    proc.kill()
