"""Sidetone on Windows itself, as Claude Code started from PowerShell would run it:
python -I tests/win_check.py   (on GitHub's Windows machines, .github/workflows/windows.yml)

In an empty home: the installer's steps build the hook program and register the hooks; the hook
program, given a session's start with no hub running, starts the real hub itself (through WMI);
then a streamed line, a follow-up waking the listener, a permission answered, and the stop check
all go through it. Prints what happened and exits 1 if any step failed.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
home = tempfile.mkdtemp(prefix="cs-win-")
# The runner's own profile (a throwaway machine): with another one, the C# compiler cannot sign.
env = {**os.environ, "CS_STATE": os.path.join(home, "state"), "XDG_CONFIG_HOME": os.path.join(home, "config"),
       "SIDETONE_TERMINAL": "off"}
run = env["CS_RUN"] = os.path.join(home, "run")
os.environ.update(env)
failed = []


def check(what, ok, detail=""):
    print(("  ok    " if ok else "  FAIL  ") + what + (f"  ({detail})" if detail else ""))
    if not ok:
        failed.append(what)


sys.path.insert(0, os.path.join(ROOT, "hub"))
import install_win  # noqa: E402

program = install_win.build_hook(sys.executable)
check("hook program built", os.path.isfile(program), program)
backup = install_win.write_settings(add=True)
with open(install_win.settings_path()) as f:
    hooks = json.load(f)["hooks"]
check("hooks registered", hooks["MessageDisplay"][0]["hooks"][0] == {"timeout": 5, "type": "command", "command": program, "args": ["display"]})


def hook(word, payload, wait=30):
    return subprocess.run([program, word], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=wait)


def ev(event, **extra):
    return {"hook_event_name": event, "session_id": "s1", "cwd": r"C:\work\api-server", **extra}


started = time.time()
hook("report-start", ev("SessionStart"))
addr = os.path.join(run, "hub.addr")
check("the hook program started the hub", os.path.exists(addr), f"{time.time() - started:.1f} s")
if not os.path.exists(addr):
    print(open(os.path.join(home, "state", "hub.log")).read() if os.path.exists(os.path.join(home, "state", "hub.log")) else "no hub.log")
    sys.exit(1)
port, token = open(addr).read().split()


def ask(path, body=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Sidetone-Token": token})
    with urllib.request.urlopen(request, timeout=5) as r:
        return json.loads(r.read() or b"null")


state = ask("/state")
check("the session is there, named after its folder", [s["name"] for s in state["sessions"]] == ["api-server"], state["sessions"])

times = []
for _ in range(10):
    t = time.time()
    hook("display", ev("MessageDisplay", delta="plain words\n"))
    times.append(time.time() - t)
check("a batch with no line passes quickly", sorted(times)[5] < 0.5, f"{sorted(times)[5] * 1000:.0f} ms median, with Python's own start")
shown = hook("display", ev("MessageDisplay", delta='<speak title="Login test">All forty two tests pass.</speak>\nmore'))
check("a spoken line is rewritten", "\U0001f50a All forty two tests pass." in shown.stdout, shown.stdout.strip()[:120])

reminder = hook("reminder", ev("UserPromptSubmit", prompt="hi"))
check("the reminder", reminder.stdout.startswith("VOICE MODE:"), reminder.stdout[:60])

listened = {}
listener = threading.Thread(target=lambda: listened.update(done=hook("listen", ev("Stop"), 60)))
listener.start()
time.sleep(2)
ask("/follow-up", {"text": "run the tests again", "session": "api-server", "delay": 0})
listener.join(20)
done = listened.get("done")
check("words spoken to it wake the listener", bool(done) and done.returncode == 2 and "run the tests again" in done.stderr,
      done and (done.returncode, done.stderr[:80]))

answered = {}
asking = threading.Thread(target=lambda: answered.update(done=hook("permission", ev(
    "PermissionRequest", tool_name="Bash", tool_input={"command": "npm test", "description": "Run tests"}), 60)))
asking.start()
time.sleep(2.5)
ask("/decide", {"decision": "allow"})
asking.join(20)
done = answered.get("done")
check("a permission answered from the hub", bool(done) and '"allow"' in done.stdout, done and done.stdout[:100])

os.makedirs(os.path.join(run, "stop"), exist_ok=True)
open(os.path.join(run, "stop", "s1"), "w").close()
stopped = hook("stop", ev("PreToolUse", tool_name="Bash"))
check("the cancel key ends the turn", '"continue": false' in stopped.stdout.replace('":false', '": false'), stopped.stdout[:80])

sys.path.insert(0, os.path.join(ROOT, "hub"))
import overlay  # noqa: E402
built = overlay.build_native(os.path.join(ROOT, "overlay", "Overlay.cs"), print)
check("the overlay builds", bool(built), built)

install_win.write_settings(add=False)
with open(install_win.settings_path()) as f:
    check("uninstall takes the hooks out", "hooks" not in json.load(f))
print("hub.log:")
print(open(os.path.join(home, "state", "hub.log")).read()[-1500:])
import re  # noqa: E402
for pid in re.findall(r"hub started pid=(\d+)", open(os.path.join(home, "state", "hub.log")).read()):
    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
sys.exit(1 if failed else 0)
