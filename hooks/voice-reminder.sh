#!/usr/bin/env bash
# UserPromptSubmit hook: asks Claude to open its final message with a short <speak> line.
[ -e "$HOME/.claude/voice-off" ] && exit 0
# With titles on (the default; "titles": "auto" in config.json turns them off) the tag also carries
# a title for the session, which the overlay shows beside its name.
config=${XDG_CONFIG_HOME:-$HOME/.config}/claude-speaks/config.json
if [ -f "$config" ] && [ "$(jq -r '.titles // "ask"' "$config" 2>/dev/null)" = auto ]; then
  echo 'VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak>...</speak>, max 2 short sentences, plain spoken English, no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). Use the tag only for that line; never write it anywhere else.'
  exit 0
fi
echo 'VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak title="...">...</speak>. Inside the tag: max 2 short sentences, plain spoken English, no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). The title: 2 to 5 plain words that name what this session is working on, such as "Login page redesign". It is shown beside the session in a list of sessions, so it must tell this one apart from others in the same project: name the task, not the project and not the last step. Keep the same title from turn to turn and change it only when the work has moved on to something else. Use the tag only for that line; never write it anywhere else.'
