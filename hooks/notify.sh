#!/usr/bin/env bash
# Notification hook: Claude is waiting on you. The hub marks the session and says so;
# without a hub, says "I need your input" directly.
input=$(cat)
. "${BASH_SOURCE[0]%/*}/lib.sh"
hub_post /event <<<"$input" >/dev/null 2>&1 && exit 0
voice_off && exit 0
. "$CS_ROOT/hooks/tts-lib.sh"
tts_say "I need your input"
exit 0
