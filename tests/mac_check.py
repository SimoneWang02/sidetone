"""Pictures of the macOS overlay, for a person to look at: python3 tests/mac_check.py PROGRAM OUT_DIR

Runs on a Mac (GitHub's macOS machines, .github/workflows/mac.yml, or one at hand). Starts the
compiled overlay (`swiftc -O -o PROGRAM overlay/mac/*.swift`), feeds it the same made-up sessions
as tests/overlay_check.py feeds the Windows one, and takes a picture of each view with macOS's
`screencapture`, cut to the overlay's windows and a margin of what is behind them, so the glass
shows. The views have the Windows pictures' names, to be put side by side.
"""
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
program, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)

proc = subprocess.Popen([program], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
heard: "queue.Queue[dict]" = queue.Queue()


def read():
    for line in proc.stdout:
        try:
            heard.put(json.loads(line))
        except ValueError:
            print("  (not JSON)", line.strip())


threading.Thread(target=read, daemon=True).start()


def send(**message):
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def wait(kind, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            msg = heard.get(timeout=max(0.05, end - time.time()))
        except queue.Empty:
            break
        if msg.get("type") == kind:
            return msg
        if msg.get("type") in ("note", "error"):
            print("  overlay:", msg.get("message"))
    return None


def shot(name, settle=0.9, pad=28):
    time.sleep(settle)
    send(type="bounds")
    b = wait("bounds", 10) or {}
    pieces = b.get("pieces") or []
    if not pieces:
        print(f"  {name}.png: nothing on screen")
        return
    x0 = min(p[0] for p in pieces) - pad
    y0 = min(p[1] for p in pieces) - pad
    x1 = max(p[0] + p[2] for p in pieces) + pad
    y1 = max(p[1] + p[3] for p in pieces) + pad
    x0, y0 = max(0, x0), max(0, y0)
    rect = f"{int(x0)},{int(y0)},{int(x1 - x0)},{int(y1 - y0)}"
    path = os.path.join(out, name + ".png")
    done = subprocess.run(["screencapture", "-x", "-R" + rect, path], capture_output=True, text=True)
    print(f"  {name}.png  pieces {pieces}  open: {b.get('open')}  scale {b.get('scale')}" + (f"  !! {done.stderr.strip()}" if done.returncode else ""))


def voice(seconds, step=0.04):
    return [round(max(0.0, min(1.0, abs(math.sin(i * 0.55)) * (0.6 + 0.4 * math.sin(i * 0.13)) * (0 if i % 37 > 30 else 1))), 3)
            for i in range(int(seconds / step))]


COLORS = ["#8AB4FF", "#FFA24D", "#B07CFF", "#7FDBCA", "#FF8FA3"]


def sessions(speaking=None, focus="api-server", waiting=None, stopping=None, context=None):
    rows = [
        dict(name="sidetone", title="Glass overlay redesign", state="done", text="Pushed, all up to date.", meta="",
             details=[["Context", "7%", 0.07, ""], ["Total Tokens", "1.4M", None, ""], ["Total Time", "2h05", None, ""], ["Tasks", "", None, ""]]),
        dict(name="api-server", title="Fix the flaky login test", state="working", text="Running the tests", meta="6m",
             details=[["Context", "56%", 0.56, ""], ["Total Tokens", "310k", None, ""], ["Total Time", "48m", None, ""], ["Tasks", "3/5", 0.6, ""]]),
        dict(name="web-app", title="Dark mode for settings", state="needs_you", text="asks: Which drink would you like?", meta="",
             details=[["Context", "83%", 0.83, "warn"], ["Total Tokens", "96k", None, ""], ["Total Time", "9m", None, ""], ["Tasks", "2/9", 0.22, ""]]),
        dict(name="data-pipeline", title="Nightly export", state="failed", text="error: rate limit", meta=""),
        dict(name="notes", title="", state="idle", text="", meta=""),
    ]
    for row, color in zip(rows, COLORS):
        row["color"] = color
        row["speaking"] = row["name"] == speaking
        row["target"] = row["name"] == focus
        row["waiting"] = (waiting or {}).get(row["name"], 0)
        row["context"] = (context or {}).get(row["name"])
        if row["name"] == stopping:
            row["text"] = "Stopping at its next step"
    return rows


HISTORY = [dict(ago="", name="api-server", color=COLORS[1], text="All forty two tests pass.", tokens="64k", kind="done", missed=False),
           dict(ago="", name="web-app", color=COLORS[2], text="Which drink would you like?", tokens="", kind="needs_you", missed=True),
           dict(ago="", name="data-pipeline", color=COLORS[3], text="I hit an error: rate limit", kind="failed", missed=False)]
SAID = "All forty two tests pass. The flaky one was a race in the login mock, which I fixed."
KEYS = {"toggle": "Ctrl+Alt+F9", "talk": "Ctrl+Alt+Space", "allow": "Ctrl+Alt+Y", "deny": "Ctrl+Alt+N", "mute": "Ctrl+Alt+M"}
DRINKS = ["Tea", "Coffee, with milk and one sugar, in the large cup that is still in the cupboard above the sink", "Water"]

# Something busy behind the glass, and its windows up before the first picture.
backdrop = subprocess.Popen(["swift", os.path.join(ROOT, "tests", "mac_backdrop.swift")], stdout=subprocess.PIPE, text=True)
backdrop.stdout.readline()
time.sleep(1)

if not wait("ready", 30):
    print("  !! the overlay did not start")
    proc.kill()
    sys.exit(1)
print("  overlay ready")
subprocess.run(["screencapture", "-x", os.path.join(out, "desktop.png")])

HERE = dict(monitor=0, corner="top-right", offset_x=60, offset_y=140)
send(type="config", still=True, mode="dots", hotkeys=KEYS, **HERE)
send(type="state", sessions=sessions(), history=HISTORY)
shot("closed")
send(type="peek", on=True)
shot("open")
send(type="peek", on=False)

send(type="flash", state="done", name="api-server", text=SAID, seconds=8)
send(type="state", sessions=sessions("api-server"), history=HISTORY)
send(type="wave", name="api-server", levels=voice(10), step=0.04, delay=0.0)
shot("speaking-closed", 1.2)
send(type="peek", on=True)
shot("speaking-open", 0.6)
send(type="peek", on=False)
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(0.3)

send(type="request", name="web-app", color=COLORS[2], text="asks: Which drink would you like?", question="Which drink would you like?", place="",
     options=DRINKS, detail="", keys="", more=0, hints=[["Ctrl+Alt+1", "answers", "3"]])
shot("question")
send(type="request", name="web-app", color=COLORS[2], text="wants to: Push to the remote", detail="git push origin main",
     keys="", hints=[["Ctrl+Alt+Y", "allow", ""], ["Ctrl+Alt+N", "deny", ""]], more=1)
shot("permission")
send(type="request")

send(type="talk", state="listening", name="web-app")
send(type="mic", levels=voice(6, 0.05), step=0.05)
shot("talk-listening", 1.2)
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6)
shot("talk-sent")
send(type="state", sessions=sessions(focus="api-server", stopping="api-server"), history=HISTORY)
send(type="talk", state="stopped", name="api-server", text="Stopping at its next step", seconds=6)
shot("stopping", 0.6)
send(type="talk")

WAITING = {"api-server": 1, "web-app": 3, "data-pipeline": 12}
CONTEXT = {"sidetone": 7, "api-server": 56, "web-app": 83, "data-pipeline": 100}
USAGE = [["5H", 41, ""], ["7D", 86, "warn"]]
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY, usage=USAGE)
send(type="peek", on=True)
shot("metrics", 1.6)
send(type="peek", on=False)
send(type="config", mode="focus")
send(type="state", sessions=sessions(context=CONTEXT), history=HISTORY, usage=USAGE)
shot("focus-only", 0.8)
send(type="config", mode="list")
shot("list", 0.6)
send(type="config", mode="dots")
send(type="state", sessions=sessions(), history=HISTORY, muted=True)
send(type="banner", icon="muted", text="Voice is muted", hint="Ctrl+Alt+M turns it on", seconds=5)
shot("mute-banner", 0.6)
send(type="banner")

send(type="config", layout="island", island_x=0.5, island_y=40)
send(type="state", sessions=sessions(), history=HISTORY)
shot("island-rest")
send(type="peek", on=True)
shot("island-open")
send(type="peek", on=False)
send(type="config", layout="bar", glass_color="#3A2E48", working_color="#B388FF", size=125)
shot("own-colors-size-125")
send(type="config", glass_color="", working_color="#4FC3F7", size=100, glass_clear=90)
shot("glass-clear-90")
backdrop.kill()
time.sleep(0.5)
shot("on-black")
send(type="config", glass_clear=50, opaque=True)
shot("solid")
send(type="config", opaque=False)

with open(os.path.join(ROOT, "tests", "mac_settings.json")) as f:
    SETTINGS = json.load(f)
for section in SETTINGS:
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section=section["name"], title="Sidetone")
    shot("settings-" + section["name"].lower(), 1.0, pad=8)
send(type="settings", open=False)
time.sleep(0.3)
subprocess.run(["screencapture", "-x", os.path.join(out, "full-screen.png")])
backdrop.kill()
proc.stdin.close()
try:
    proc.wait(5)
    print("  exited with", proc.returncode, "when its input closed")
except subprocess.TimeoutExpired:
    print("  !! still running after its input closed")
    proc.kill()
