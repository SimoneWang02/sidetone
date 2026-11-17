"""Manual check of the overlay window from WSL: python3 tests/overlay_check.py OUT_DIR [--glass]

Starts the overlay by itself, feeds it made-up content, and saves a PNG of each view to OUT_DIR.
The window is drawn opaque and only its own rectangle is captured, so nothing else on the
screen ends up in the pictures. With --glass it also checks the real see-through glass: for a
few seconds it puts a striped test card of its own behind the overlay and captures that, so
again nothing of the screen is in the picture. It uses spare hotkeys so it can run next to the
live overlay.
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
sys.path.insert(0, f"{ROOT}/hub")
import overlay  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
out = os.path.abspath(args[0] if args else ".")
os.makedirs(out, exist_ok=True)


def win(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()


command = overlay.command(f"{ROOT}/overlay/overlay.ps1", lambda line: print(" ", line))
print("  starting", os.path.basename(command[0]))
proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd="/mnt/c/Windows")
replies = queue.Queue()
threading.Thread(target=lambda: [replies.put(line.decode(errors="replace").strip()) for line in proc.stdout], daemon=True).start()


def send(**message):
    if message.get("type") == "config":  # the user may be holding Ctrl+Alt just now; that must not open the panel here
        message.setdefault("focus_wheel", "")
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


def capture(name, pieces, pad=0):
    """Save a picture of just these screen rectangles (x, y, w, h), on black, in their real arrangement."""
    x0, y0 = min(p[0] for p in pieces) - pad, min(p[1] for p in pieces) - pad
    x1, y1 = max(p[0] + p[2] for p in pieces) + pad, max(p[1] + p[3] for p in pieces) + pad
    copies = "".join(f"$g.CopyFromScreen({x},{y},{x - x0},{y - y0},(New-Object System.Drawing.Size {w},{h})); "
                     for x, y, w, h in ([(x0, y0, x1 - x0, y1 - y0)] if pad else pieces))
    script = (f"Add-Type -AssemblyName System.Drawing; $b = New-Object System.Drawing.Bitmap {x1 - x0},{y1 - y0}; "
              f"$g = [System.Drawing.Graphics]::FromImage($b); $g.Clear([System.Drawing.Color]::Black); {copies}"
              f"$b.Save('{win(out)}\\{name}.png')")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], cwd="/mnt/c/Windows")
    return x0, y0, x1 - x0, y1 - y0


def bounds():
    send(type="bounds")
    return wait("bounds", 5)


def shot(name, settle=0.9):
    """Capture the overlay's own rectangles. If it changed size meanwhile, the picture could hold
    a strip of the screen behind it, so it is taken again, and dropped if it never holds still."""
    time.sleep(settle)
    for _ in range(4):
        b = bounds()
        if not b or not b.get("visible"):
            print(f"  {name}: not visible")
            return b
        capture(name, b["pieces"])
        after = bounds()
        if after and after.get("pieces") == b["pieces"]:
            break
        time.sleep(0.5)
    else:
        os.remove(os.path.join(out, f"{name}.png"))
        print(f"  {name}: kept changing size, no picture kept")
        return b
    print(f"  {name}.png  pieces {b['pieces']}  open: {b.get('open')}  monitor {b.get('monitor')}  catches mouse: {b.get('catches_mouse')}")
    return b


# A striped card with text, shown behind the overlay for a few seconds without taking focus.
BACKDROP = r"""
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
$w = New-Object System.Windows.Window
$w.WindowStyle = 'None'; $w.ResizeMode = 'NoResize'; $w.ShowActivated = $false; $w.ShowInTaskbar = $false; $w.Topmost = $true
$w.WindowStartupLocation = 'Manual'; $w.Left = %d; $w.Top = %d; $w.Width = %d; $w.Height = %d
$p = New-Object System.Windows.Controls.WrapPanel
$colors = '#FFFFFF','#F4F4F4','#1E88E5','#FFFFFF','#E53935','#FDD835','#FFFFFF','#43A047','#111111','#FFFFFF'
for ($i = 0; $i -lt 60; $i++) {
  $t = New-Object System.Windows.Controls.TextBlock
  $t.Text = 'The quick brown fox jumps over the lazy dog 0123456789'
  $t.Width = 360; $t.FontSize = 15; $t.Padding = '6,3,6,3'
  $t.Background = $colors[$i %% $colors.Length]
  $t.Foreground = if ($colors[$i %% $colors.Length] -in '#111111','#1E88E5','#E53935','#43A047') { 'White' } else { 'Black' }
  [void]$p.Children.Add($t)
}
$w.Content = $p
$w.Add_ContentRendered({ [Console]::Out.WriteLine('up') })
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(%d)
$timer.Add_Tick({ $w.Close() })
$timer.Start()
[void]$w.ShowDialog()
"""


def glass_shot(name, seconds=12):
    """Capture the see-through overlay over our own test card (never over the user's screen)."""
    b = bounds()
    if not b or not b.get("visible"):
        print(f"  {name}: not visible")
        return
    pad = 14
    x0, y0 = min(p[0] for p in b["pieces"]) - pad, min(p[1] for p in b["pieces"]) - pad
    x1, y1 = max(p[0] + p[2] for p in b["pieces"]) + pad, max(p[1] + p[3] for p in b["pieces"]) + pad
    card = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", BACKDROP % (x0 - 30, y0 - 30, x1 - x0 + 60, y1 - y0 + 60, seconds)],
                            cwd="/mnt/c/Windows", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    up = card.stdout.readline().strip() == b"up"  # blocks until the card is drawn (or its process ended)
    time.sleep(2.6)  # the overlay climbs back on top of the card (it does so every 2 s)
    after = bounds()
    if up and card.poll() is None and after and after.get("pieces") == b["pieces"]:
        capture(name, b["pieces"], pad)
        if card.poll() is None:
            print(f"  {name}.png  (over the test card)")
        else:  # the card left while the picture was being taken
            os.remove(os.path.join(out, f"{name}.png"))
            print(f"  {name}: the test card closed too early, no picture kept")
    else:
        print(f"  {name}: the test card was not up or the overlay moved, no picture taken")
    card.wait()


def voice(seconds, step=0.04):
    """Made-up loudness of a voice: syllables with pauses."""
    return [round(max(0.0, min(1.0, abs(math.sin(i * 0.55)) * (0.6 + 0.4 * math.sin(i * 0.13)) * (0 if i % 37 > 30 else 1))), 3)
            for i in range(int(seconds / step))]


def sessions(speaking=None, focus="api-server"):
    rows = [
        dict(name="claude-speaks", title="Glass overlay redesign", state="done", text="Pushed, all up to date.", meta=""),
        dict(name="api-server", title="Fix the flaky login test", state="working", text="Running the tests", meta="3/5 · 6m"),
        dict(name="web-app", title="Dark mode for settings", state="needs_you", text="asks: Which drink would you like?", meta=""),
        dict(name="data-pipeline", title="Nightly export", state="failed", text="error: rate limit", meta=""),
        dict(name="notes", title="", state="idle", text="", meta=""),
    ]
    for row, color in zip(rows, ["#8AB4FF", "#FFB86B", "#C6A0F6", "#7FDBCA", "#FF8FA3"]):
        row["color"] = color
        row["speaking"] = row["name"] == speaking
        row["target"] = row["name"] == focus
    return rows


HISTORY = [dict(ago="now", name="api-server", color="#FFB86B", text="All forty two tests pass."),
           dict(ago="3m", name="web-app", color="#C6A0F6", text="The login page is fixed and ready for review."),
           dict(ago="12m", name="data-pipeline", color="#7FDBCA", text="I hit an error: rate limit")]
KEYS = {"toggle": "Ctrl+Alt+F9"}
SAID = "All forty two tests pass. The flaky one was a race in the login mock, which I fixed."

if not wait("ready", 40):
    proc.kill()
    sys.exit(1)


def say(seconds, **config):
    send(type="flash", state="done", name="api-server", text=SAID, seconds=seconds)
    send(type="state", sessions=sessions("api-server"), history=HISTORY)
    send(type="wave", name="api-server", levels=voice(seconds + 3), step=0.04, delay=0.0)


# Away from the corners, where the live overlay usually sits (it would show up in the pictures).
HERE = dict(monitor=0, corner="bottom-right", offset_x=420, offset_y=260)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, **HERE)
send(type="state", sessions=sessions(), history=HISTORY)
shot("closed")
say(3)
shot("speaking-closed", 1.6)
send(type="peek", on=True)
shot("speaking-open", 0.6)
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(2.5)
shot("open", 0.3)
send(type="peek", on=False)
send(type="request", name="web-app", color="#C6A0F6", text="asks: Which drink would you like?", detail="1  Tea   2  Coffee   3  Water",
     keys="Ctrl+Alt+1 to Ctrl+Alt+3 answers  \u00b7  question 1 of 2")
shot("question")
send(type="request", name="web-app", text="wants to: Push to the remote", detail="git push origin main",
     keys="Ctrl+Alt+Y allow  \u00b7  Ctrl+Alt+N deny")
shot("permission")
send(type="request")
send(type="talk", state="listening", name="web-app")
send(type="mic", levels=voice(4, 0.05), step=0.05)
shot("talk-listening", 1.5)
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6)
shot("talk-sent")
send(type="peek", on=True)
shot("talk-sent-open", 0.5)
send(type="peek", on=False)
send(type="talk", state="failed", name="web-app", text="did not catch that", seconds=4)
shot("talk-failed", 0.5)
send(type="talk")
send(type="mode", mode="list")
send(type="peek", on=True)
shot("list-history")
send(type="peek", on=False)
send(type="mode", mode="dots")
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, monitor=1, corner="bottom-left", offset_x=30, offset_y=30)
say(3)
shot("second-monitor-left", 1.6)
send(type="state", sessions=sessions(), history=HISTORY)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, **HERE)
send(type="move")
shot("move")
send(type="move", on=False)

# The island layout: at rest, with a session speaking, and with the details out.
send(type="move", on=False)
for layout in ("island",):
    send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout=layout, **HERE)
    send(type="state", sessions=sessions(), history=HISTORY)
    shot(f"{layout}-rest", 1.2)
    say(3)
    shot(f"{layout}-speaking", 1.2)
    send(type="state", sessions=sessions(), history=HISTORY)
    send(type="flash", name="api-server", text="", seconds=0)
    send(type="peek", on=True)
    shot(f"{layout}-open", 1.0)
    send(type="peek", on=False)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout="bar", **HERE)

if "--glass" in sys.argv:
    for kind in ("blur", "acrylic"):
        send(type="config", opaque=False, glass=kind, mode="dots", hotkeys=KEYS, monitor=0, corner="top-right", offset_x=60, offset_y=140)
        say(9)
        time.sleep(1.0)
        glass_shot(f"glass-{kind}-closed")
        send(type="state", sessions=sessions(), history=HISTORY)
        send(type="flash", name="api-server", text="", seconds=0)  # the sentence is over, so the row is one line again
        send(type="peek", on=True)
        time.sleep(0.8)
        glass_shot(f"glass-{kind}-open")
        send(type="peek", on=False)
        time.sleep(0.3)

proc.stdin.close()
try:
    print("  exited with", proc.wait(5), "when its input closed")
except subprocess.TimeoutExpired:
    print("  !! did not exit when its input closed")
    proc.kill()
