"""Manual check of the overlay window from WSL: python3 tests/overlay_check.py OUT_DIR [--glass] [--only=NAME]

Starts the overlay by itself, feeds it made-up content, and saves a PNG of each view to OUT_DIR.
The window is drawn opaque, and its picture is asked from the window itself, not copied from
the screen (tests/overlay_capture.ps1), so nothing else on the screen ends up in the pictures:
not what is behind the overlay and not what lies over it, such as the live overlay, which can
be anywhere. The check proves that to itself at the start: it lays a window of one color of
its own over the overlay and the picture must hold none of that color (proof-*.png).
With --glass it also checks the real see-through glass, which only exists on the screen: for a
few seconds it puts a striped test card of its own behind the overlay and copies that from the
screen, and a picture is dropped if any always-on-top window of another program reached into
it. It uses spare hotkeys so it can run next to the live overlay, and sends that one nothing.
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
import state  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
# --only=settings: keep only the pictures whose names begin so, and skip the waits and the proof
# for the rest (for looking at one view again and again while working on it).
ONLY = next((a[7:] for a in sys.argv[1:] if a.startswith("--only=")), "")
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


# The one process that takes all the pictures (see overlay_capture.ps1 for what it is asked).
camera = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win(f"{ROOT}/tests/overlay_capture.ps1")],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd="/mnt/c/Windows")
answers = queue.Queue()
threading.Thread(target=lambda: [answers.put(line.decode(errors="replace").strip()) for line in camera.stdout], daemon=True).start()


def ask(timeout=30, **request):
    """One request to the camera and its answer; {"ok": False, ...} when there is none."""
    if request:
        camera.stdin.write((json.dumps(request) + "\n").encode())
        camera.stdin.flush()
    end = time.time() + timeout
    while time.time() < end:
        try:
            return json.loads(answers.get(timeout=0.2))
        except queue.Empty:
            if camera.poll() is not None:
                break
        except ValueError:
            continue
    return {"ok": False, "error": "the camera did not answer"}


def capture(name, pieces, process=None):
    """Save a picture of the overlay's own windows at these rectangles (x, y, w, h), on black,
    in their real arrangement. Asked from the windows, so what covers them is not in it."""
    answer = ask(do="window", path=f"{win(out)}\\{name}.png", pieces=pieces, process=process)
    if not answer.get("ok"):
        print(f"  {name}: no picture, {answer.get('error')}")
    return bool(answer.get("ok"))


def screen(name, pieces, pad=0, ours=()):
    """Save a copy of the screen around these rectangles. Returns the always-on-top windows of
    other programs that reached into it (a list; empty = the picture holds only our own), or
    None when there is no picture."""
    answer = ask(do="screen", path=f"{win(out)}\\{name}.png", pieces=pieces, pad=pad, ours=list(pieces) + list(ours))
    if not answer.get("ok"):
        print(f"  {name}: no picture, {answer.get('error')}")
        return None
    return answer.get("foreign") or []


def drop(name):
    try:
        os.remove(os.path.join(out, f"{name}.png"))
    except OSError:
        pass


def bounds():
    send(type="bounds")
    return wait("bounds", 5)


def shot(name, settle=0.9):
    """Capture the overlay's own rectangles. If it changed size meanwhile, the picture could hold
    a strip of the screen behind it, so it is taken again, and dropped if it never holds still."""
    if ONLY and not name.startswith(ONLY):
        return bounds()
    time.sleep(settle)
    for _ in range(4):
        b = bounds()
        if not b or not b.get("visible"):
            print(f"  {name}: not visible")
            return b
        taken = capture(name, b["pieces"], b.get("process"))
        after = bounds()
        if taken and after and after.get("pieces") == b["pieces"]:
            break
        time.sleep(0.5)
    else:
        drop(name)
        print(f"  {name}: kept changing size or could not be taken, no picture kept")
        return b
    print(f"  {name}.png  pieces {b['pieces']}  open: {b.get('open')}  monitor {b.get('monitor')}  catches mouse: {b.get('catches_mouse')}")
    return b


# A window of one plain color, laid over the overlay for a few seconds without taking focus:
# it stands in for anything that may lie over it on the screen, such as the live overlay.
DECOY = "#FF00FF"
COVER = r"""
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
Add-Type -Namespace Place -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int w, int h, uint flags); [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][Place.Win]::SetProcessDPIAware()  # pixels mean the same here as in the overlay and the camera
$w = New-Object System.Windows.Window
$w.WindowStyle = 'None'; $w.ResizeMode = 'NoResize'; $w.ShowActivated = $false; $w.ShowInTaskbar = $false; $w.Topmost = $true
$x = %d; $y = %d; $wide = %d; $high = %d
$w.WindowStartupLocation = 'Manual'; $w.Left = $x; $w.Top = $y; $w.Width = $wide; $w.Height = $high
# The place is in the screen's own pixels, as the overlay reports it, and WPF's Left and Top are
# in its own units (the screen's pixels over the display scale, 2.5 here): set again in pixels
# once the window exists. Without it the window lay elsewhere and nothing was proved.
$w.Add_SourceInitialized({
  $h = (New-Object System.Windows.Interop.WindowInteropHelper $w).Handle
  [void][Place.Win]::SetWindowPos($h, [IntPtr](-1), $x, $y, $wide, $high, 0x10)  # -1 on top of all, 0x10 without taking focus
})
$inside = New-Object System.Windows.Controls.Border  # a window with nothing in it never says it was drawn
$inside.Background = '%s'
$w.Content = $inside
$w.Add_ContentRendered({ [Console]::Out.WriteLine('up') })
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromSeconds(%d)
$timer.Add_Tick({ $w.Close() })
$timer.Start()
[void]$w.ShowDialog()
"""


def prove(name="proof", seconds=10):
    """Show that a picture of the overlay holds nothing of what lies over it on the screen.

    A window of one color is laid over the overlay. A copy of the screen must then show that
    color (it really is in the way), and the picture asked from the overlay's windows must
    show none of it. Both pictures are kept. Returns True when that is so."""
    b = bounds()
    if not b or not b.get("visible"):
        print(f"  {name}: the overlay is not visible, nothing proved")
        return False
    pieces, pad = b["pieces"], 40
    x0, y0 = min(p[0] for p in pieces) - pad, min(p[1] for p in pieces) - pad
    x1, y1 = max(p[0] + p[2] for p in pieces) + pad, max(p[1] + p[3] for p in pieces) + pad
    for attempt in range(4):
        cover = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", COVER % (x0, y0, x1 - x0, y1 - y0, DECOY, seconds)],
                                 cwd="/mnt/c/Windows", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        up = cover.stdout.readline().strip() == b"up"
        # The overlay climbs back over the cover every two seconds, so the screen is copied
        # right away, while the cover is on top, and once more after the picture.
        covered = 0
        if up and cover.poll() is None:
            screen(f"{name}-screen", pieces)
            covered = ask(do="count", path=f"{win(out)}\\{name}-screen.png", color=DECOY).get("count", 0)
            taken = capture(f"{name}-window", pieces, b.get("process"))
            still_up = cover.poll() is None and bounds().get("pieces") == pieces
            inside = ask(do="count", path=f"{win(out)}\\{name}-window.png", color=DECOY) if taken else {}
            if not still_up:  # the cover left meanwhile: the copy of the screen may hold the screen itself
                drop(f"{name}-screen")
        cover.kill()
        cover.wait()
        if up and covered and taken and still_up:
            share = 100 * covered // max(1, inside.get("of", 1))
            print(f"  {name}: a {DECOY} window lay over the overlay ({share}% of {name}-screen.png is that color); "
                  f"{name}-window.png, asked from the overlay itself, holds {inside.get('count')} dots of it")
            return inside.get("count") == 0
        drop(f"{name}-screen")
        time.sleep(1.0)
    print(f"  {name}: could not get the cover over the overlay, nothing proved")
    return False


# A striped card with text, shown behind the overlay for a few seconds without taking focus.
BACKDROP = r"""
Add-Type -AssemblyName PresentationFramework,PresentationCore,WindowsBase
Add-Type -Namespace Place -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int w, int h, uint flags); [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][Place.Win]::SetProcessDPIAware()  # pixels mean the same here as in the overlay and the camera
$w = New-Object System.Windows.Window
$w.WindowStyle = 'None'; $w.ResizeMode = 'NoResize'; $w.ShowActivated = $false; $w.ShowInTaskbar = $false; $w.Topmost = $true
$x = %d; $y = %d; $wide = %d; $high = %d
$w.WindowStartupLocation = 'Manual'; $w.Left = $x; $w.Top = $y; $w.Width = $wide; $w.Height = $high
# The place is in the screen's own pixels, as the overlay reports it, and WPF's Left and Top are
# in its own units (the screen's pixels over the display scale, 2.5 here): set again in pixels
# once the window exists. Without it the window lay elsewhere and nothing was proved.
$w.Add_SourceInitialized({
  $h = (New-Object System.Windows.Interop.WindowInteropHelper $w).Handle
  [void][Place.Win]::SetWindowPos($h, [IntPtr](-1), $x, $y, $wide, $high, 0x10)  # -1 on top of all, 0x10 without taking focus
})
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
    behind = (x0 - 30, y0 - 30, x1 - x0 + 60, y1 - y0 + 60)
    card = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", BACKDROP % (*behind, seconds)],
                            cwd="/mnt/c/Windows", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    up = card.stdout.readline().strip() == b"up"  # blocks until the card is drawn (or its process ended)
    time.sleep(2.6)  # the overlay climbs back on top of the card (it does so every 2 s)
    after = bounds()
    if up and card.poll() is None and after and after.get("pieces") == b["pieces"]:
        for attempt in range(3):  # something of another program in the way (the live overlay talking, say) may be gone in a moment
            others = screen(name, b["pieces"], pad, ours=[behind])
            if not others:
                break
            drop(name)
            time.sleep(1.5)
        if others is None:
            pass
        elif others:
            print(f"  {name}: no picture kept, on the screen there was in the way: "
                  + "; ".join(sorted({f"{o.get('process') or o.get('kind')} at {o.get('area')}" for o in others})))
        elif card.poll() is None:
            print(f"  {name}.png  (over the test card)")
        else:  # the card left while the picture was being taken
            drop(name)
            print(f"  {name}: the test card closed too early, no picture kept")
    else:
        print(f"  {name}: the test card was not up or the overlay moved, no picture taken")
    card.kill()
    card.wait()


def voice(seconds, step=0.04):
    """Made-up loudness of a voice: syllables with pauses."""
    return [round(max(0.0, min(1.0, abs(math.sin(i * 0.55)) * (0.6 + 0.4 * math.sin(i * 0.13)) * (0 if i % 37 > 30 else 1))), 3)
            for i in range(int(seconds / step))]


def sessions(speaking=None, focus="api-server", waiting=None, stopping=None, context=None):
    """The rows the hub would send. `waiting`: session name -> messages held for it; `stopping`:
    the name of a session that was asked to end its turn; `context`: session name -> how full
    its context is, in percent."""
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
        row["waiting"] = n = (waiting or {}).get(row["name"], 0)
        row["context"] = (context or {}).get(row["name"])
        if row["name"] == stopping:
            row["text"] = "Stopping at its next step"
    return rows


COLORS = state.COLORS[:5]  # as five sessions would have them
HISTORY_TIMED = [dict(ago="now", name="api-server", color=COLORS[1], text="All forty two tests pass.", tokens="64k", kind="done", missed=False),
           dict(ago="2m", name="web-app", color=COLORS[2], text="Which drink would you like?", tokens="", kind="needs_you", missed=True),
           dict(ago="3m", name="web-app", color=COLORS[2], text="The login page is fixed and ready for review. I also moved the styles into one file so the dark mode has a single place to change.", tokens="1.2k", kind="done", missed=False),
           dict(ago="9m", name="web-app", color=COLORS[2], text="I can't read the clock from a side question.", tokens="", kind="aside", missed=False),
           dict(ago="14m", name="web-app", color=COLORS[2], text="Half way: the settings page is done.", tokens="", kind="progress", missed=True),
           dict(ago="12m", name="data-pipeline", color=COLORS[3], text="I hit an error: rate limit", kind="failed", missed=False)]
HISTORY = [dict(ago="", name="api-server", color=COLORS[1], text="All forty two tests pass.", tokens="64k", kind="done", missed=False),
           dict(ago="", name="web-app", color=COLORS[2], text="Which drink would you like?", tokens="", kind="needs_you", missed=True),
           dict(ago="", name="web-app", color=COLORS[2], text="The login page is fixed and ready for review. I also moved the styles into one file so the dark mode has a single place to change.", tokens="1.2k", kind="done", missed=False),
           dict(ago="", name="web-app", color=COLORS[2], text="I can't read the clock from a side question.", tokens="", kind="aside", missed=False),
           dict(ago="", name="web-app", color=COLORS[2], text="Half way: the settings page is done.", tokens="", kind="progress", missed=True),
           dict(ago="", name="data-pipeline", color=COLORS[3], text="I hit an error: rate limit", kind="failed", missed=False)]
KEYS = {"toggle": "Ctrl+Alt+F9"}
SAID = "All forty two tests pass. The flaky one was a race in the login mock, which I fixed."

if not wait("ready", 40) or not ask(timeout=60).get("ready"):
    print("  !! the overlay or the camera did not start")
    proc.kill()
    camera.kill()
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
send(type="peek", on=True)
time.sleep(1.2)
proved = None if ONLY else prove()
send(type="peek", on=False)
say(3)
shot("speaking-closed", 1.6)
send(type="peek", on=True)
shot("speaking-open", 0.6)
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(2.5)
shot("open", 0.3)
send(type="peek", on=False)
DRINKS = ["Tea", "Coffee, with milk and one sugar, in the large cup that is still in the cupboard above the sink", "Water"]


def question(text, options, ticked=None, place="", more=0):
    """A question as Hub._show_request sends it: one answer to pick, or with `ticked` several to tick."""
    keys = f"Ctrl+Alt+1 to Ctrl+Alt+{len(options)} " + ("tick    Ctrl+Alt+Y confirms" if ticked is not None else "answers")
    send(type="request", name="web-app", color=COLORS[2], text=f"asks: {text}", question=text, place=place, options=options,
         detail="\n".join(f"{i}  {o}" for i, o in enumerate(options, 1)),
         keys=keys + (f"    {more} more waiting" if more else ""), more=more,
         hints=[["Ctrl+Alt+1", "tick" if ticked is not None else "answers", str(len(options))]]
               + ([["Ctrl+Alt+Y", "confirms", ""]] if ticked is not None else []),
         **({"ticked": ticked} if ticked is not None else {}))


question("Which drink would you like?", DRINKS)
shot("question")
send(type="config", choice_caps=True)  # the numbers as key caps, a setting
question("Which drink would you like?", DRINKS)
shot("question-caps")
send(type="config", choice_caps=False)
# One of two questions in the same dialog: which one it is stands beside the name.
question("Which drink would you like?", DRINKS, place="1 of 2")
shot("question-one-of-two")
# Several choices to tick: a box before each, none ticked yet, then two of them.
TOPPINGS = ["Mushrooms", "Olives, the green ones from the jar that is already open", "Peppers", "Onions"]
question("Which toppings do you want on it?", TOPPINGS, ticked=[False] * 4)
shot("question-tick-none")
question("Which toppings do you want on it?", TOPPINGS, ticked=[True, False, True, False], place="2 of 2", more=1)
shot("question-tick-some")
send(type="request", name="web-app", color=COLORS[2], text="wants to: Push to the remote", detail="git push origin main",
     keys="Ctrl+Alt+Y allow    Ctrl+Alt+N deny", hints=[["Ctrl+Alt+Y", "allow", ""], ["Ctrl+Alt+N", "deny", ""]], more=0)
shot("permission")
# Another request behind it: said on a line of its own under the keys, as for a question.
send(type="request", name="web-app", color=COLORS[2], text="wants to: Push to the remote", detail="git push origin main",
     keys="Ctrl+Alt+Y allow    Ctrl+Alt+N deny    2 more waiting", hints=[["Ctrl+Alt+Y", "allow", ""], ["Ctrl+Alt+N", "deny", ""]], more=2)
shot("permission-more")
send(type="request")
send(type="talk", state="listening", name="web-app")
send(type="mic", levels=voice(4, 0.05), step=0.05)
shot("talk-listening", 1.5)
# Another session starts to speak in the very moment you start to talk (its line is cut at once).
send(type="flash", state="done", name="api-server", text=SAID, seconds=4)
send(type="state", sessions=sessions("api-server", focus="sidetone"), history=HISTORY)
send(type="wave", name="api-server", levels=voice(2), step=0.04, delay=0.0)
shot("talk-while-another-speaks", 0.5)
send(type="state", sessions=sessions(focus="sidetone"), history=HISTORY)
shot("talk-after-the-other-was-cut", 0.5)
# Words that waited are handed to a session while another one is speaking: a sign on its light,
# and the bubble stays with the sentence that is being said.
send(type="flash", state="done", name="api-server", text=SAID, seconds=4)
send(type="state", sessions=sessions("api-server", focus="sidetone"), history=HISTORY)
send(type="wave", name="api-server", levels=voice(2), step=0.04, delay=0.0)
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6, quiet=True)
shot("talk-handed-over-while-another-speaks", 0.5)
send(type="state", sessions=sessions(focus="sidetone"), history=HISTORY)
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6)
shot("talk-sent")
send(type="peek", on=True)
shot("talk-sent-open", 0.5)
send(type="peek", on=False)
send(type="talk", state="failed", name="web-app", text="Didn't catch that", seconds=4)
shot("talk-failed", 0.5)
send(type="talk", state="transcribing", name="web-app")
shot("talk-transcribing", 0.5)
# A side question being answered by a copy of the session.
send(type="talk", state="aside", name="web-app", text="By the way, which file was that?", hint="Answering on the side\u2026")
shot("talk-aside", 0.5)
# Words for a busy session: they wait, and its light carries the number from then on.
HELD = "Also add a test for the empty input case."
send(type="state", sessions=sessions(focus="api-server", waiting={"api-server": 1}), history=HISTORY)
send(type="talk", state="queued", name="api-server", text=HELD, seconds=6)
shot("talk-queued", 0.8)
send(type="peek", on=True)
shot("talk-queued-open", 0.5)
send(type="peek", on=False)
# A session asked to end its turn: the stop sign in its light, and its row says so.
send(type="state", sessions=sessions(focus="api-server", stopping="api-server"), history=HISTORY)
send(type="talk", state="stopped", name="api-server", text="Stopping at its next step", seconds=6)
shot("stopping", 0.5)
send(type="peek", on=True)
shot("stopping-open", 0.5)
send(type="peek", on=False)
send(type="talk")
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(0.4)

# Words waiting for a session, marked on its light: one message, several, and more than nine.
WAITING = {"api-server": 1, "web-app": 3, "data-pipeline": 12}


def look(**settings):
    """The overlay with these settings for the mark, and the hub's own defaults for the rest of
    them: the overlay keeps a setting it is not sent again, so each look names them all."""
    mark = {key: value for key, value in overlay.DEFAULTS.items() if key.startswith("waiting_")}
    send(type="config", opaque=True, still=settings.pop("still", True), mode="dots", hotkeys=KEYS, **HERE, **{**mark, **settings})


def marks(name, waiting=WAITING, opened=True, settle=0.8):
    send(type="state", sessions=sessions(waiting=waiting), history=HISTORY)
    shot(name, settle)
    if opened:
        send(type="peek", on=True)
        shot(f"{name}-open", 0.6)
        send(type="peek", on=False)
    send(type="state", sessions=sessions(), history=HISTORY)  # nothing waits any more, so the next look starts afresh
    time.sleep(0.3)


marks("waiting")  # the number in the upper right; above nine a dismayed face
look(waiting_many="number")
marks("waiting-nine-plus", opened=False)
look(waiting_size=6.6, waiting_color="#FF6E8A")
marks("waiting-small-pink", opened=False)
look(waiting_mark="clock")
marks("waiting-clock", opened=False)
look(waiting_mark="clock", waiting_many="number")
marks("waiting-clock-nine-plus", opened=False)
look(waiting_mark="dot")
marks("waiting-dot", opened=False)
# The number as it first shows itself, across the whole light. That is a motion, so this one
# picture is taken with motion on, and the number is held there for longer than the check takes.
look(still=False, waiting_cover="each", waiting_hold=60)
marks("waiting-covers-the-light", opened=False, settle=1.6)
look()
# The whole overlay drawn smaller and bigger (overlay.size): closed, with the details out, and
# with a session speaking, so the bubble's width and place show too.
for size in (75, 150):
    look(size=size)
    send(type="state", sessions=sessions(), history=HISTORY)
    shot(f"size-{size}", 0.8)
    send(type="peek", on=True)
    shot(f"size-{size}-open", 0.6)
    send(type="peek", on=False)
    say(3)
    shot(f"size-{size}-speaking", 1.6)
    send(type="state", sessions=sessions(), history=HISTORY)
    time.sleep(0.5)
look()
# Colors of one's own (2026-11-23): every status light, and the glass, in colors other than
# the hub's, closed and with the details out; then the hub's own colors again.
OWN_COLORS = dict(working_color="#B388FF", needs_you_color="#FF7043", done_color="#26C6DA",
                  failed_color="#F06292", idle_color="#7A7A7A", glass_color="#3A2E48")
look(**OWN_COLORS)
send(type="state", sessions=sessions(), history=HISTORY)
shot("own-colors", 0.8)
send(type="peek", on=True)
shot("own-colors-open", 0.6)
send(type="peek", on=False)
look(**{key: overlay.DEFAULTS[key] for key in OWN_COLORS})
# How full each session's context is, as an arc around its light: nearly empty, about half,
# past the warning, full, and one that is not known; then with words waiting on top of it.
CONTEXT = {"sidetone": 7, "api-server": 56, "web-app": 83, "data-pipeline": 100}
send(type="state", sessions=sessions(context=CONTEXT), history=HISTORY)
shot("context")
send(type="peek", on=True)
shot("context-open", 0.6)
send(type="peek", on=False)
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY)
shot("context-waiting")
# A session's figures in a line of their own under the rows: of the session in focus, and
# of the one the mouse is on (which has four of them).
USAGE = [["5H", 41, ""], ["7D", 86, "warn"]]  # the plan's usage, at the foot of the card
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY, usage=USAGE)
send(type="peek", on=True)
shot("metrics", 0.6)
send(type="peek", on=True, over="web-app")
shot("metrics-other", 0.6)
# The two bars side by side, as they were at first.
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, usage_layout="line", **HERE)
send(type="peek", on=True, over="web-app")
shot("metrics-usage-line", 0.6)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, usage_layout="rows", **HERE)
send(type="peek", on=True, over="web-app")
# With the week of one model as a third bar at the foot.
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY, usage=USAGE[:1] + [["7D", 47, ""], ["Fable", 89, "warn"]])
shot("metrics-model", 0.6)
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY, usage=USAGE)
send(type="peek", on=True, over="sidetone")
shot("metrics-unknown", 0.6)
# The mouse was on web-app last; then the focus moves to another session: the card follows it.
send(type="peek", on=True, over="web-app")
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING, focus="sidetone"), history=HISTORY)
shot("metrics-follows-focus", 0.6)
send(type="state", sessions=sessions(context=CONTEXT, waiting=WAITING), history=HISTORY)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, monitor=0, corner="top-right", offset_x=420, offset_y=260)
send(type="peek", on=True, over="web-app")
shot("metrics-under", 1.0)  # a bar in the upper half: the card is under the rows
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, details_style="line", **HERE)
send(type="peek", on=True, over="web-app")
shot("metrics-line", 0.6)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, details_style="tiles", **HERE)
send(type="peek", on=False)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout="island", **HERE)
send(type="state", sessions=sessions(context=CONTEXT), history=HISTORY)
shot("context-island", 1.2)
send(type="peek", on=True, over="web-app")
shot("metrics-island", 1.0)
send(type="peek", on=False)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout="bar", **HERE)
send(type="state", sessions=sessions(), history=HISTORY)
time.sleep(0.3)
# The settings window, one picture for each of its sections, with what a new install has.
import base  # noqa: E402
import settings as settings_mod  # noqa: E402


class FakeHub:
    cfg = base.Config(run="", state="", whisper_language="en,it")  # Chinese switched off
    lock = threading.Lock()
    sessions = type("Open", (), {"by_id": {n: type("S", (), {"name": n}) for n in ("sidetone", "api-server", "web-app")}})
    speech = type("Queue", (), {"engine": None})  # nothing to time with: the times below stand in
    _voice_times = {"kokoro:en-us": 0.51, "kokoro:en-gb": 0.54, "kokoro:it": 0.53, "piper:it_IT-paola-medium": 0.37, "zh": 0.64}

    def voices(self):
        kokoro = ("af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky am_adam "
                  "am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa bf_alice bf_emma bf_isabella bf_lily "
                  "bm_daniel bm_fable bm_george bm_lewis if_sara im_nicola zf_xiaobei zf_xiaoni zm_yunjian").split()
        return {"choosable": True, "builtin": kokoro, "custom": ["my_mix"], "pool": list(state.VOICE_POOL),
                "piper": ["piper:en_US-lessac-medium", "piper:it_IT-paola-medium"],
                "zh": [f"zh:z{k}_{n:03d}" for k, n in (("f", 49), ("f", 6), ("m", 56), ("m", 57), ("f", 1), ("m", 9))],
                "projects": {"sidetone": "af_heart", "api-server": "bm_fable", "web-app": "af_bella"}}

    def _voice_for(self, s, lang, text=""):  # what the hub would give: the first of the language's voices
        return settings_mod.in_use(self, lang)[0]


SETTINGS = settings_mod.describe(FakeHub())
# The tool's mark, large, as the overlay draws it (the same drawing as in the window and the taskbar).
if not ONLY or "settings".startswith(ONLY) or "logo".startswith(ONLY):
    send(type="logo", path=f"{win(out)}\\logo.png", size=512)
    print("  logo.png:", "saved" if wait("logo", 5) else "NOT saved")
    for name, size in (("logo-icon", 256), ("logo-icon-32", 32), ("logo-icon-24", 24)):  # as the taskbar shows it
        send(type="logo", path=f"{win(out)}\\{name}.png", size=size, tile=True)
        print(f"  {name}.png:", "saved" if wait("logo", 5) else "NOT saved")
for section in SETTINGS:
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section=section["name"])
    shot("settings-" + section["name"].lower(), 0.7)
# A color's list of ready colors, dropped down by a click on the Working dot: a window of its
# own, whose place is reported with the settings window's.
if not ONLY or "settings-colors-open".startswith(ONLY) or ONLY.startswith("settings-colors"):
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Colors", click=[644, 109])
    shot("settings-colors-open", 0.8)
    # Its last place, the wheel, swaps the ready colors for the picker (row 2, column 5 of 30-unit
    # places, inside the list's 6 units of edge). In the same message as the click that opens the
    # list: the window is filled anew by each message, which shuts it.
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Colors", click=[644, 109], click_list=[141, 51])
    shot("settings-colors-picker", 0.8)
# Voices at the height of the screen, with Chinese unfolded: the window maximized by its button.
if not ONLY or "settings-voices-tall".startswith(ONLY) or ONLY.startswith("settings-voices"):
    # The button that makes it as big as the screen, and then the same button again, which is
    # then at the screen's right edge: 58 of the window's own units from its right side (the
    # window is 790 wide, SettingsWindow.Broad; Windows' display scale on top).
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices")
    normal = bounds()["pieces"][1]
    scale = normal[2] / 790
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[732, 24])
    tall = shot("settings-voices-tall", 0.7)["pieces"][1]
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[round(tall[2] / scale) - 58, 24])
    time.sleep(0.5)
    if bounds()["pieces"][1] != normal:
        print("  !! the settings window did not come back to its size")
    # English opened by a click on its heading, then closed again.
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[400, 142])
    shot("settings-voices-open", 0.7)
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[400, 142])
    # Italian opened: Piper's voice with its "Faster" tag.
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[400, 208])
    shot("settings-voices-italian", 0.7)
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Voices", click=[400, 208])
# Chinese as a pack (2026-11-23): not installed with its size and Install, coming in, failed;
# then installed and opened, with the voices not downloaded yet and Remove under its card.
if not ONLY or "settings-pack".startswith(ONLY) or ONLY.startswith("settings-pack"):
    import tempfile  # noqa: E402

    import packs  # noqa: E402

    class PackEngine:
        dir = piper_dir = tempfile.mkdtemp(prefix="cs-pack-")

        def __init__(self, zh):
            self.zh = set(zh)

        def zh_voices(self):
            return self.zh

    class PackHub(FakeHub):
        def __init__(self, zh, languages="en,it"):
            self.speech = type("Queue", (), {"engine": PackEngine(zh)})()
            self.cfg = base.Config(run="", state="", whisper_model="small", whisper_language=languages)
            self.zh = zh

        def voices(self):
            return {**FakeHub.voices(self), "zh": ["zh:" + v for v in self.zh]}

    def pack_shot(name, hub, click=None):
        sections = settings_mod.describe(hub)
        send(type="settings", open=True, quiet=True, sections=sections, section="Voices")
        if click:
            send(type="settings", open=True, quiet=True, sections=sections, section="Voices", click=click)
        shot(name, 0.7)
        if click:
            send(type="settings", open=True, quiet=True, sections=sections, section="Voices", click=click)

    hub = PackHub([])
    pack_shot("settings-pack-missing", hub)
    pack_shot("settings-pack-listen", hub, click=[400, 244])  # opened: its voices, heard from recordings
    settings_mod.jobs(hub)["zh"] = {"busy": True, "done": 141_000_000, "total": 428_000_000, "step": "Chinese model", "error": ""}
    pack_shot("settings-pack-installing", hub)
    settings_mod.jobs(hub)["zh"] = {"busy": False, "done": 0, "total": 0, "step": "", "error": "could not download kokoro-v1.1-zh.onnx: timed out"}
    pack_shot("settings-pack-failed", hub)
    for f, size in zip(packs.ZH_FILES, (packs.ZH_MODEL[1], 4 * 522_000, packs.ZH_CONFIG[1])):  # what Remove says it frees
        with open(os.path.join(PackEngine.dir, f), "wb") as blank:
            blank.truncate(size)
    pack_shot("settings-pack-off", PackHub(["zf_049", "zf_006", "zm_056", "zm_057"], "en,it"))  # installed, off: Remove under it
    hub = PackHub(["zf_049", "zf_006", "zm_056", "zm_057"], "en,it,zh")
    settings_mod.jobs(hub)["zh:zm_030"] = {"busy": True, "done": 200_000, "total": 523_500, "step": "", "error": ""}
    # At the height of the screen, Chinese opened and its More Voices shown: the voices not
    # downloaded, with their size, and Remove under the card.
    sections = settings_mod.describe(hub)
    send(type="settings", open=True, quiet=True, sections=sections, section="Voices")
    normal = bounds()["pieces"][1]
    scale = normal[2] / 790
    # Maximized, the column is centered: the places below are read off a first picture.
    for at in ([732, 24], [826, 229], [520, 506]):
        send(type="settings", open=True, quiet=True, sections=sections, section="Voices", click=at)
        time.sleep(0.3)
    tall = shot("settings-pack-installed", 0.7)["pieces"][1]
    # Remove under the card: with six voices listed, so that it fits on the screen.
    most, settings_mod.MOST_VOICES = settings_mod.MOST_VOICES, 6
    send(type="settings", open=True, quiet=True, sections=settings_mod.describe(hub), section="Voices")
    settings_mod.MOST_VOICES = most
    shot("settings-pack-remove", 0.7)
    for at in ([520, 506], [826, 229], [round(tall[2] / scale) - 58, 24]):
        send(type="settings", open=True, quiet=True, sections=sections, section="Voices", click=at)
        time.sleep(0.3)
CHANGED =[{**s, "changed": s["name"] == "Speech"} for s in SETTINGS]  # one setting of Speech moved: its reset button lit
send(type="settings", open=True, quiet=True, sections=CHANGED, section="Speech")
shot("settings-voice-changed", 0.7)
# What is drawn answers to a click: one on a choice, a switch, a section at the left, a
# hotkey. The places are read off the pictures above (the window's own units, from its corner).
def click(section, x, y, expect):
    send(type="settings", open=True, quiet=True, sections=SETTINGS, section=section, click=[x, y])
    got = wait("setting", 3)
    told = (got.get("key"), got.get("value")) if got else None
    print(f"  click in {section} at {x},{y}: {told}" + ("" if told == expect else f"   !! expected {expect}"))
    return told == expect


clicks = [click("Overlay", 716, 117, ("overlay.layout", "island")),
          click("Talking", 735, 117, ("followup_when", "end"))]
send(type="settings", open=True, quiet=True, sections=SETTINGS, section="Speech", click=[46, 245])  # "Keys" at the left
shot("settings-clicked-keys", 0.5)
send(type="settings", open=True, quiet=True, sections=SETTINGS, click=[690, 230])  # the hotkey of "Keep the details out"
shot("settings-typing-key", 0.5)
print("  the settings window answers to clicks:", "yes" if all(clicks) else "NO (see above)")
send(type="settings", open=False)
time.sleep(0.3)
# The same steps with the sign at the right of the session's line instead of in its light.
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, talk_sign="line")
send(type="talk", state="sent", name="web-app", text="Also add a test for the empty input case.", seconds=6)
shot("talk-sent-line", 0.5)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, talk_sign="light")
send(type="talk")
send(type="mode", mode="list")
send(type="peek", on=True)
shot("list-history")
send(type="peek", on=True, over="web-app")
shot("list-history-other")
send(type="state", sessions=sessions(), history=HISTORY_TIMED)  # with `history_time` on: how long ago, before the tokens
send(type="peek", on=True, over="web-app")
shot("list-history-timed")
send(type="state", sessions=sessions(), history=HISTORY)
send(type="config", opaque=True, still=True, mode="list", hotkeys=KEYS, history="all", **HERE)
send(type="peek", on=True, over="web-app")
shot("list-history-all")  # every session's lines mixed: under the card, with their names
send(type="config", opaque=True, still=True, mode="list", hotkeys=KEYS, history="session", **HERE)
# Details "Selected Session": the card and only the row of the session it is about, its sentence
# in full; the other rows left out.
send(type="peek", on=False)
send(type="config", opaque=True, still=True, mode="focus", hotkeys=KEYS, **HERE)
say(6)
shot("focus-only", 1.2)
send(type="config", opaque=True, still=True, mode="list", hotkeys=KEYS, **HERE)
send(type="peek", on=False)
send(type="mode", mode="dots")
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, monitor=1, corner="bottom-left", offset_x=30, offset_y=30)
say(3)
shot("second-monitor-left", 1.6)
send(type="state", sessions=sessions(), history=HISTORY)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, **HERE)
send(type="banner", icon="muted", text="Voice is muted", hint="Ctrl+Alt+M turns it on")
shot("mute-off", 0.6)
send(type="banner", icon="voice", text="Voice is on", hint="")
shot("mute-on", 0.6)
send(type="banner", icon="clear", text="Clear sidetone?", hint="Ctrl+Alt+C to confirm")  # the clear key asks
shot("clear-ask", 0.6)
send(type="banner", icon="clearing", text="Clearing sidetone\u2026", hint="")
shot("clear-under-way", 0.6)
send(type="banner", icon="clearing", text="Clearing sidetone\u2026", hint="waiting for the editor")
shot("clear-slow", 0.6)
send(type="banner", icon="cleared", text="Cleared sidetone", hint="")
shot("clear-done", 0.6)
send(type="banner", text=None)
send(type="state", sessions=sessions(), history=HISTORY, muted=True)
send(type="peek", on=True)
shot("mute-line", 0.8)
send(type="config", **{**dict(opaque=True, still=True, mode="dots", hotkeys=KEYS, **HERE), "muted_line": False, "muted_card_icon": True})
send(type="state", sessions=sessions(), history=HISTORY, muted=False)
shot("mute-none", 0.8)
send(type="state", sessions=sessions(), history=HISTORY, muted=True)
shot("mute-icon", 0.8)
send(type="peek", on=False)
send(type="flash", name="api-server", state="done", text="All forty two tests pass. The flaky one was a race in the login mock.", seconds=30)
shot("mute-bubble", 0.8)
send(type="peek", on=True)
send(type="config", **{**dict(opaque=True, still=True, mode="dots", hotkeys=KEYS, **HERE), "muted_line": True, "muted_card_icon": False})
send(type="peek", on=False)
send(type="state", sessions=sessions(), history=HISTORY, muted=False)
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
# Dragged to the lower left: it opens upward, and nothing leaves the screen.
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout="island", island_x=0.03, island_y=1200, **HERE)
send(type="peek", on=True)
shot("island-moved-open", 1.0)
send(type="peek", on=False)
send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, layout="bar", island_x=0.5, island_y=10, **HERE)

def free_place(room=420):
    """A place for the glass views where no always-on-top window of another program is: those
    views are copied from the screen, and the live overlay can be anywhere on it. `room` is how
    far the panel, the bubble and the test card reach around the bar."""
    places = [dict(monitor=0, corner=corner, offset_x=x, offset_y=y)
              for x, y in ((60, 140), (460, 300), (900, 420)) for corner in ("top-right", "bottom-right", "bottom-left", "top-left")]
    for place in places:
        send(type="config", opaque=True, still=True, mode="dots", hotkeys=KEYS, **place)
        time.sleep(0.5)
        b = bounds()
        if not b or not b.get("visible"):
            continue
        others = ask(do="others", pieces=b["pieces"], pad=room, ours=b["pieces"]).get("foreign")
        if others == []:
            return place
        print(f"  glass: not at {place['corner']} {place['offset_x']},{place['offset_y']}, in the way there: "
              + "; ".join(sorted({str(o.get("process") or o.get("kind")) for o in others or [{"kind": "no answer"}]})))
    return None


# A character beside the bubble (2026-11-25, overlay.character): each kind, on the bubble's edge
# and inside it, speaking, needing you, done and failed. Held still, so each picture is the
# moment's first frame; the sheets are drawn here as the hub would draw them.
if not ONLY or ONLY.startswith("character"):
    import characters  # noqa: E402
    folder = os.path.join(overlay.windows_folder() or out, "characters")
    os.makedirs(folder, exist_ok=True)
    SHEETS = {}
    for style in characters.STYLES:
        for color in COLORS:
            path = os.path.join(folder, f"check-{style}-{color.lstrip('#')}.png")
            with open(path, "wb") as f:
                f.write(characters.sheet(style, characters.kind_of(color), color))
            SHEETS[style, color] = win(path)
    MOMENTS = [("speaking", "api-server", "done", SAID), ("needs", "web-app", "needs_you", "asks: Which drink would you like?"),
               ("done", "sidetone", "done", "Pushed, all up to date."), ("failed", "data-pipeline", "failed", "I hit an error: rate limit")]
    for style in characters.STYLES:
        for place in ("edge", "inside"):
            look(character=style, character_place=place)
            for moment, name, state, text in MOMENTS:
                rows = sessions(name if moment == "speaking" else None)
                for row in rows:
                    row["sprite"] = SHEETS[style, row["color"]]
                    if row["name"] == name and moment != "speaking":
                        row["state"] = state
                send(type="state", sessions=rows, history=HISTORY, sprite_layout=characters.LAYOUT)
                send(type="flash", state=state, name=name, text=text, seconds=6)
                if moment == "speaking":
                    send(type="wave", name=name, levels=voice(9), step=0.04, delay=0.0)
                shot(f"character-{style}-{place}-{moment}", 1.4)
                send(type="flash", name=name, text="", seconds=0)
                time.sleep(0.6)
    look(character="none")

if "--glass" in sys.argv:
    spot = free_place()
    if not spot:
        print("  glass: no place on the first screen is free of other programs' always-on-top windows, no glass pictures")
    for kind in ("blur", "acrylic") if spot else ():
        send(type="config", opaque=False, glass=kind, mode="dots", hotkeys=KEYS, **spot)
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
ask(timeout=1, do="quit")
try:
    camera.wait(5)
except subprocess.TimeoutExpired:
    camera.kill()
print("  pictures hold only the overlay under test:", "not checked (--only)" if ONLY else "proved" if proved else "NOT PROVED (see above)")
sys.exit(0 if proved or ONLY else 1)
