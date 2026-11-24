# Trying Sidetone on Windows itself (no WSL)

For Claude Code started from PowerShell, cmd or Windows Terminal. (Under WSL nothing changes:
`install.sh` inside WSL, as now.) It has run only on GitHub's Windows machines; this is the list
for the first real try. Write what you find under each point; a session picks it up from here.

## Install

1. Claude Code for Windows, in PowerShell: `irm https://claude.ai/install.ps1 | iex`, then open a
   new terminal, run `claude` once and log in.
2. uv: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`,
   then open a new terminal.
3. The branch: `git clone -b mac-overlay https://github.com/SimoneWang02/sidetone.git $HOME\sidetone`
   (with Git for Windows; or download the branch as a zip from GitHub and unpack it there).
4. `cd $HOME\sidetone; powershell -ExecutionPolicy Bypass -File install.ps1 -Languages en,it`
5. Start Claude Code in any folder. The lights appear at the top right.

If something fails: `%USERPROFILE%\.local\state\sidetone\hub.log`. To take it out again:
`powershell -ExecutionPolicy Bypass -File uninstall.ps1`. If you also use it under WSL, run only one
of the two at a time (both have the same keys).

## What to check

- [ ] The lights appear with the first session, and each reply's line is said.
      How long after the reply does the voice start? (The PC under WSL: 0.8 s)
- [ ] Streaming feels as smooth as before (each streamed batch passes through the hook program,
      about 20 ms).
- [ ] Push-to-talk: hold Ctrl+Alt+Space, speak, let go; your words reach the session.
- [ ] Words spoken while it works reach it after its next step, and Ctrl+Alt+Backspace stops it.
- [ ] A permission prompt answered with Ctrl+Alt+Y and Ctrl+Alt+N.
- [ ] Ctrl+Alt+S: the settings window, as under WSL.
- [ ] The VS Code extension, if you use VS Code there: going to a terminal moves the focus.
- [ ] Two sessions at once: each its own light and voice.
- [ ] Close every session: the hub stops by itself after 30 minutes.

## Findings

(write here)
