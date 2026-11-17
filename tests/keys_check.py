"""Manual check from WSL that a held talk key is kept from other programs: python3 tests/keys_check.py

Starts an overlay of its own with the talk key on F20 (a key no keyboard has and no program
uses, pressed here by Windows itself, with no Ctrl or Alt, so nothing the user is doing is
touched). Then it presses F20, repeats it the way a held key repeats, and lets go, while a
second program watches which of those presses the overlay passes on. (It watches before
Windows matches hotkeys, so it shows what the overlay itself holds back, which is what counts
once Ctrl or Alt has been let go and the hotkey no longer matches.)

Two rounds:
1. The hook is in before the key goes down (`keep_talk_key: always`; with the usual keys it is
   in as soon as Ctrl and Alt are down). Expected: nothing at all is passed on, neither press
   nor repeats nor release, the overlay reports both holds, and the key is not left stuck.
2. The hook comes too late, as when the talk key goes down in the same instant as Ctrl and
   Alt (`keep_talk_key: held` with a key that has no Ctrl or Alt). Expected: only the first
   press and the release are passed on ("down up"), the overlay reports the hold, the key is
   not left stuck, and the press after the hold is passed on again in full.
3. A hotkey with a second key, as Ctrl and Alt are for the real one; left Shift stands in for
   them here (for about a fifth of a second Windows takes Shift for held, so do not type just
   then). Expected: nothing of the talk key is passed on, during the hold Windows takes Shift
   for up although it is still held (so a click would be a plain click), and the second hold,
   begun without letting go of Shift, is still recognised.
4. Another key (F19) is tapped during the hold, after which a keyboard no longer repeats the
   held key. Expected: the hold goes on until the talk key is let go, and nothing is passed on.
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


def round_(keep, expected, what, talk="F20", modifier=0, hidden=None, other=0):
    """Hold the key once with the overlay set to `keep`; True if other programs saw `expected`
    (and, with a `modifier` held as well, if Windows took that key for `hidden` during the hold)."""
    send(type="config", opaque=True, still=True, mode="dots", focus_wheel="", drag_keys="", hotkeys={"talk": talk},
         keep_talk_key="off", monitor=0, corner="bottom-right", offset_x=420, offset_y=260)
    for m in drain(1.0):
        if m.get("type") == "error":
            print("  overlay error:", m.get("message"))
    watcher = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win(f"{ROOT}/tests/keys_check.ps1"),
         "-Repeats", str(REPEATS), "-Delay", "1500", "-Modifier", str(modifier), "-Other", str(other)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="/mnt/c/Windows")
    if watcher.stdout.readline().strip() != "hooked":
        print("  !! the watcher did not start:", watcher.stderr.read()[:300])
        return False
    send(type="config", keep_talk_key=keep)  # the overlay's hook, if it puts one in now, comes after the watcher's
    out, err = watcher.communicate(timeout=60)
    seen, state, held = (out.strip("\r\n").split(" | ") + ["", ""])[:3]  # nothing passed on leaves the first part empty
    hotkeys = [m.get("name") for m in drain(1.0) if m.get("type") == "hotkey"]
    print(f"  {what}")
    print("    the overlay passed on:", seen or "(nothing)", err.strip()[:300])
    print("    the overlay reported:", " ".join(hotkeys) or "(nothing)")
    print("    the key afterwards:", state)
    if modifier:
        print("    the other key during the hold, as Windows had it:", held)
    good = seen == expected and hotkeys == ["talk", "talk_end"] * 2 and state == "released" and (hidden is None or held == hidden)
    print("    OK" if good else f"    !! expected to be passed on: {expected or '(nothing)'}" + (f", the other key {hidden}" if hidden else ""))
    return good


ok = False
try:
    if not wait_ready():
        sys.exit("  !! the overlay did not start")
    first = round_("always", "", "hook in before the key goes down:")
    second = round_("held", "down up down up", "hook in only once the hold has begun:")
    # Left Shift stands in for Ctrl and Alt: held before the talk key and let go after two holds.
    third = round_("held", "", "a hotkey with a second key (Shift+F20), which is hidden while talking:",
                   talk="Shift+F20", modifier=0xA0, hidden="up")
    # F19 is tapped in the middle of the hold, as an arrow key is to move the focus while talking.
    # Had the hold ended there, the release of the talk key a second and a half later would be passed on.
    fourth = round_("always", "", "another key pressed while talking does not end the hold:", other=0x82)
    ok = first and second and third and fourth
finally:
    try:
        proc.stdin.close()
        proc.wait(5)
    except Exception:
        proc.kill()
sys.exit(0 if ok else 1)
