"""Pictures of the Linux overlay, for a person to look at: python tests/linux_check.py PYTHON OUT_DIR

Starts overlay/linux/overlay.py with the given Python (one with PySide6), feeds it the made-up
sessions tests/mac_check.py feeds the Mac one, and saves each view as the overlay draws it (its
own `shot`: the pieces in their places on a dark backdrop). Then presses the talk key with
xdotool where there is one, to see press and release arrive. Runs on a desktop, under Xvfb
(.github/workflows/linux.yml), or on WSL's own display.
"""
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
python, out = sys.argv[1], os.path.abspath(sys.argv[2])
os.makedirs(out, exist_ok=True)
proc = subprocess.Popen([python, os.path.join(ROOT, "overlay", "linux", "overlay.py")], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, text=True, bufsize=1)
heard = queue.Queue()


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


def shot(name, settle=0.8, pad=0):
    time.sleep(settle)
    path = os.path.join(out, name + ".png")
    send(type="shot", path=path)
    got = wait("shot", 10) or {}
    send(type="bounds")
    b = wait("bounds", 10) or {}
    print(f"  {name}.png  {'saved' if got.get('path') else 'NOTHING'}  pieces {b.get('pieces')}  open: {b.get('open')}  on {b.get('platform')}")


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

if not wait("ready", 30):
    print("  !! the overlay did not start")
    proc.kill()
    sys.exit(1)
print("  overlay ready")
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
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(0.3)
send(type="request", name="web-app", color=COLORS[2], text="asks: Which drink would you like?", question="Which drink would you like?",
     place="", options=DRINKS, detail="", keys="", more=0, hints=[["Ctrl+Alt+1", "answers", "3"]])
shot("question")
send(type="request", name="web-app", color=COLORS[2], text="wants to: Push to the remote", detail="git push origin main",
     keys="", hints=[["Ctrl+Alt+Y", "allow", ""], ["Ctrl+Alt+N", "deny", ""]], more=1)
shot("permission")
send(type="request")
send(type="talk", state="listening", name="web-app")
send(type="mic", levels=voice(6, 0.05), step=0.05)
shot("talk-listening", 1.0)
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6)
shot("talk-sent")
send(type="talk")
WAITING = {"api-server": 1, "web-app": 3, "data-pipeline": 12}
CONTEXT = {"sidetone": 7, "api-server": 56, "web-app": 83, "data-pipeline": 100}
USAGE = [["5H", 41, ""], ["7D", 86, "warn"]]
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY, usage=USAGE)
send(type="peek", on=True)
shot("metrics", 1.6)
send(type="peek", on=False)
send(type="config", mode="focus")
shot("focus-only", 0.8)
send(type="config", mode="dots")
send(type="state", sessions=sessions(), history=HISTORY, muted=True)
send(type="banner", icon="muted", text="Voice is muted", hint="Ctrl+Alt+M turns it on", seconds=5)
shot("mute-banner", 0.6)
send(type="banner")
send(type="config", layout="island", island_x=0.5, island_y=40)
send(type="peek", on=True)
shot("island-open")
send(type="peek", on=False)
send(type="config", layout="bar", glass_color="#3A2E48", working_color="#B388FF", size=125)
shot("own-colors-size-125")
send(type="config", glass_color="", working_color="#4FC3F7", size=100)
with open(os.path.join(ROOT, "tests", "mac_settings.json")) as f:
    SETTINGS = json.load(f)
for section in SETTINGS:
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section=section["name"], title="Sidetone")
    shot("settings-" + section["name"].lower(), 1.0)
send(type="settings", open=False)
if shutil.which("xdotool") and os.environ.get("DISPLAY"):
    while not heard.empty():
        heard.get()
    subprocess.run(["xdotool", "keydown", "ctrl+alt+space"])
    time.sleep(0.4)
    subprocess.run(["xdotool", "keyup", "space", "keyup", "alt", "keyup", "ctrl"])
    got = []
    end = time.time() + 4
    while time.time() < end and len(got) < 2:
        msg = wait("hotkey", max(0.1, end - time.time()))
        if msg:
            got.append(msg.get("name"))
    print("  keys: Ctrl+Alt+Space gave", got, "(talk, then talk_end, is right)")
else:
    print("  keys: no xdotool here, not pressed")
proc.stdin.close()
try:
    proc.wait(5)
    print("  exited with", proc.returncode, "when its input closed")
except subprocess.TimeoutExpired:
    print("  !! still running after its input closed")
    proc.kill()
