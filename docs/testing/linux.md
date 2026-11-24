# Trying Sidetone on a Linux desktop

Ubuntu, Fedora, or any desktop with an X11 or Wayland session. It has run only on GitHub's
Ubuntu machines, on a virtual X display; this is the list for the first real one. Write what you
find under each point; a session picks it up from here.

## Install

1. `sudo apt install jq curl pulseaudio-utils` (Fedora: `sudo dnf install jq curl pulseaudio-utils`)
2. uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. `git clone -b mac-overlay https://github.com/SimoneWang02/sidetone.git ~/sidetone`
4. `cd ~/sidetone && ./install.sh --languages en,it` (on a desktop it also installs Qt for the
   overlay, about 150 MB)
5. Start Claude Code in any folder. The lights appear at the top right.

If something fails: `~/.local/state/sidetone/hub.log` and `sidetone status`. If the overlay does
not start, Qt may be missing a system library: `sudo apt install libxcb-cursor0`.

## What to check

- [ ] Which session you are in: `echo $XDG_SESSION_TYPE` (x11 or wayland). Write it down here.
- [ ] The voice says each reply's line. How long after the reply?
- [ ] The lights stay on top of other windows, at the top right.
- [ ] Push-to-talk: hold Ctrl+Alt+Space, speak, let go.
      On Wayland the keys reach Sidetone only while one of its windows has the keyboard. Instead,
      give a key to `sidetone talk toggle` in your desktop's keyboard settings (Settings,
      Keyboard, Custom Shortcuts): once to start talking, again to send.
- [ ] The details: the mouse over the lights. Dragging the bar to another corner.
- [ ] A permission prompt answered with Ctrl+Alt+Y and Ctrl+Alt+N.
- [ ] Ctrl+Alt+S (or `sidetone settings`): the settings window.
- [ ] Two sessions at once: each its own light and voice.

## Findings

(write here)
