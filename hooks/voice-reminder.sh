#!/usr/bin/env bash
# UserPromptSubmit hook: asks Claude to open its final message with a short <speak> line.
[ -e "$HOME/.claude/voice-off" ] && exit 0
echo 'VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak>...</speak>, max 2 short sentences, plain spoken English, no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). Use the tag only for that line; never write it anywhere else.'
