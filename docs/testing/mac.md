# Trying Sidetone on a Mac

The Mac port (branch `mac-overlay`) has run only on GitHub's Macs. This is the list for the
first real one; write what you find under each point, and a session picks it up from here.

## Install

1. `xcode-select --install` (Apple's command line tools: the overlay is built with them)
2. `brew install jq uv` (Homebrew from https://brew.sh if it is not there)
3. `git clone -b mac-overlay https://github.com/SimoneWang02/sidetone.git ~/sidetone`
   (the repo is private: GitHub asks you to sign in)
4. `cd ~/sidetone && ./install.sh --languages en,it`
5. Start Claude Code in any folder. The lights appear at the top right.

If something fails: `~/.local/state/sidetone/hub.log` and `sidetone status`.

## What to check

- [ ] The voice: each reply's line is said. How long after the reply does it start?
      (GitHub's virtual Mac: 2.1 s; the PC: 0.8 s)
- [ ] Push-to-talk: hold ⌃⌥Space (Control-Option-Space), speak, let go. macOS asks once for
      the microphone, for the app Claude Code runs in. Do your words reach the session?
- [ ] The details: the mouse over the lights, and ⌃⌥ held by themselves.
- [ ] Dragging the bar to another corner; it stays there after `sidetone hub restart`.
- [ ] A permission prompt answered with ⌃⌥Y and ⌃⌥N.
- [ ] ⌃⌥S: the settings window. A switch, a slider, a color from the color well.
- [ ] The glass over a busy window (a web page), with Liquid Glass on and off
      (Overlay section; Liquid Glass needs macOS 26).
- [ ] Two sessions at once: each its own light and voice.
- [ ] Anything that looks or feels wrong next to the Windows overlay.

## Findings

(write here)
