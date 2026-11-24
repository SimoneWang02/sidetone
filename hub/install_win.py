"""The Windows install's own steps, run by install.ps1 with the environment's Python once that
is in place: the hook program built, the hooks registered in Claude Code's settings, the
overlay built, the languages chosen. Kept in Python so the hooks come from the same list as on
Linux and the Mac (hooks/settings-snippet.json) and the merging can be tested anywhere.

    python -I hub/install_win.py install [--languages en,it] [--no-download]
    python -I hub/install_win.py uninstall
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNIPPET = os.path.join(ROOT, "hooks", "settings-snippet.json")

# Each bash hook (with its option) and what the Windows hook program is told to do instead.
SCRIPTS = {"report.sh --start": "report-start", "report.sh": "report", "listen.sh": "listen", "voice-reminder.sh": "reminder",
           "stop.sh": "stop", "permission.sh": "permission", "speak.sh": "speak", "notify.sh": "notify", "display.sh": "display"}


def folder() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "sidetone")


def hook_program() -> str:
    return os.path.join(folder(), "sidetone-hook.exe")


def windows_hooks(program: str) -> dict:
    """The snippet's hooks, each bash script swapped for the hook program with its word (exec
    form: no shell at all, so Git Bash is not needed and PowerShell's slow start is avoided)."""
    with open(SNIPPET) as f:
        hooks = json.load(f)["hooks"]
    out = {}
    for event, groups in hooks.items():
        out[event] = []
        for group in groups:
            made = {k: v for k, v in group.items() if k != "hooks"}
            made["hooks"] = []
            for hook in group["hooks"]:
                script = hook["command"].split("/hooks/", 1)[1]
                entry = {k: v for k, v in hook.items() if k != "command"}
                entry.update(command=program, args=[SCRIPTS[script]])
                made["hooks"].append(entry)
            out[event].append(made)
    return out


def merged(current: dict, program: str, add: bool = True) -> dict:
    """`current` settings with our hooks put in (an earlier install's taken out first), or only
    taken out; everything else is kept as it was."""
    def ours(hook: dict) -> bool:
        return os.path.normcase(str(hook.get("command", ""))) == os.path.normcase(program)
    old = current.get("hooks") or {}
    new = windows_hooks(program) if add else {}
    hooks = {}
    for event in sorted(set(old) | set(new)):
        kept = []
        for group in old.get(event, []):
            left = [h for h in group.get("hooks", []) if not ours(h)]
            if left:
                kept.append({**group, "hooks": left})
        if kept or new.get(event):
            hooks[event] = kept + new.get(event, [])
    out = {k: v for k, v in current.items() if k != "hooks"}
    if hooks:
        out["hooks"] = hooks
    return out


def settings_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def write_settings(add: bool) -> str:
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as f:
            current = json.load(f)
    except FileNotFoundError:
        current = {}
    backup = f"{path}.bak-sidetone-{time.strftime('%Y%m%d-%H%M%S')}"
    if os.path.exists(path):
        shutil.copy2(path, backup)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(merged(current, hook_program(), add), f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".tmp", path)
    return backup


def compiler() -> str | None:
    windows = os.environ.get("WINDIR", r"C:\Windows")
    return next((c for c in (os.path.join(windows, "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe"),
                             os.path.join(windows, "Microsoft.NET", "Framework", "v4.0.30319", "csc.exe")) if os.path.isfile(c)), None)


def build_hook(python: str) -> str:
    """The hook program, made with Windows' own C# compiler, and beside it where the checkout
    and its Python are."""
    csc = compiler()
    if not csc:
        raise SystemExit("Windows' C# compiler (.NET Framework 4) was not found")
    os.makedirs(folder(), exist_ok=True)
    program = hook_program()
    done = subprocess.run([csc, "/nologo", "/optimize+", f"/out:{program}", "/r:System.Web.Extensions.dll",
                           "/r:System.Management.dll", os.path.join(ROOT, "hooks", "win", "Hook.cs")],
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("the hook program could not be built: " + (done.stdout + done.stderr)[:600])
    windowless = os.path.join(os.path.dirname(python), "pythonw.exe")
    with open(os.path.join(folder(), "hook.json"), "w", encoding="utf-8") as f:
        json.dump({"root": ROOT, "python": windowless if os.path.isfile(windowless) else python}, f, indent=2)
    return program


def main(argv: list[str]) -> int:
    action = argv[0] if argv else "install"
    if action == "uninstall":
        backup = write_settings(add=False)
        print(f"Hooks removed from {settings_path()} (backup: {backup})")
        return 0
    languages = argv[argv.index("--languages") + 1] if "--languages" in argv else ""
    nofetch = ["--no-download"] if "--no-download" in argv else []
    program = build_hook(sys.executable)
    print(f"Hook program built: {program}")
    sys.path.insert(0, HERE)
    import overlay
    if overlay.build_native(os.path.join(ROOT, "overlay", "Overlay.cs"), print):
        print("Overlay built.")
    config = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "sidetone", "config.json")
    if languages:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "packs.py"), "languages", config, languages, *nofetch])
    backup = write_settings(add=True)
    print(f"Hooks registered in {settings_path()} (backup: {backup})")
    print("Start Claude Code in any folder: the lights appear at the top right, and each reply's line is said.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
