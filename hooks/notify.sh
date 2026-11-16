#!/usr/bin/env bash
# Notification hook: says "I need your input" when Claude is waiting on you.
[ -e "$HOME/.claude/voice-off" ] && exit 0
cat >/dev/null  # drain hook JSON
. "$HOME/.claude/hooks/tts-lib.sh"
tts_say "I need your input"
exit 0
