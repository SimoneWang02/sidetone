"""The whole thing on a Mac (or a Linux desktop), as a session would start it: python3 tests/mac_hub_check.py OUT_DIR

The real hook (hooks/report.sh --start) starts the real hub in an empty home, which builds the
Swift overlay with Apple's compiler and starts it; then a few sessions' events go in, the hub
speaks with the Mac's own voice (no Kokoro here), and a picture of the screen is taken. Prints
what the hub logged. For GitHub's Macs (.github/workflows/mac.yml), where nobody can look.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
home = tempfile.mkdtemp(prefix="cs-mac-")
env = {**os.environ, "HOME": home, "CS_RUN": os.path.join(home, "run"), "CS_STATE": os.path.join(home, "state"),
       "XDG_CONFIG_HOME": os.path.join(home, "config"), "SIDETONE_TERMINAL": "off"}
sock = os.path.join(home, "run", "hub.sock")
log = os.path.join(home, "state", "hub.log")


def hook(script, payload, *args):
    return subprocess.run([os.path.join(ROOT, "hooks", script), *args], input=json.dumps(payload), text=True,
                          capture_output=True, env=env, timeout=30)


def call(path, body=None):
    cmd = ["curl", "-sf", "-m", "3", "--unix-socket", sock, f"http://hub{path}"]
    if body is not None:
        cmd += ["--data-binary", json.dumps(body)]
    done = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(done.stdout or "null") if done.returncode == 0 else None


def logged():
    try:
        with open(log) as f:
            return f.read()
    except OSError:
        return ""


def until(test, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if test():
            return True
        time.sleep(0.5)
    return False


def ev(event, sid, cwd, **extra):
    return {"hook_event_name": event, "session_id": sid, "cwd": cwd, **extra}


started = time.time()
hook("report.sh", ev("SessionStart", "a", "/work/api-server"), "--start")
print("  hub up:", until(lambda: call("/health") is not None, 30), f"after {time.time() - started:.1f} s")
for sid, cwd in (("b", "/work/web-app"), ("c", "/work/notes")):
    hook("report.sh", ev("SessionStart", sid, cwd), "--start")
hook("report.sh", ev("UserPromptSubmit", "a", "/work/api-server", prompt="fix the login test"), "--start")
built = until(lambda: any(w in logged() for w in ("overlay ready", "overlay could not", "overlay not built")), 400)
print("  overlay:", "ready" if "overlay ready" in logged() else "NOT ready", f"after {time.time() - started:.0f} s")
hook("speak.sh", ev("Stop", "b", "/work/web-app", last_assistant_message="<speak>The dark mode is done and pushed.</speak>"))
time.sleep(1.5)
state = call("/state") or {}
print("  sessions:", [(s.get("name"), s.get("state")) for s in state.get("sessions", [])])
camera = ["screencapture", "-x"] if shutil.which("screencapture") else ["import", "-window", "root"] if shutil.which("import") else None
if camera:  # macOS's own, or ImageMagick's on Linux
    subprocess.run(camera + [os.path.join(out, "hub-live.png")])
    time.sleep(4)
    subprocess.run(camera + [os.path.join(out, "hub-live-later.png")])
print("  hub.log:")
for line in logged().splitlines()[-25:]:
    print("    " + line)
try:
    with open(os.path.join(home, "state", "voice.log")) as f:
        print("  voice.log:", f.read().strip()[-600:])
except OSError:
    print("  voice.log: none")
subprocess.run(["pkill", "-f", os.path.join(ROOT, "hub", "hub.py")])
