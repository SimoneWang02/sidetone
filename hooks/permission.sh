#!/usr/bin/env bash
# PermissionRequest hook: offers the prompt to the hub, which can answer it from a hotkey while
# Claude Code's own dialog stays usable (whichever answers first wins). Prints the hub's decision,
# or nothing when the prompt was answered in the terminal. Without a hub, does nothing.
input=$(cat)
. "${BASH_SOURCE[0]%/*}/lib.sh"
[ -S "$CS_SOCK" ] || exit 0
curl -sf -m 3600 --unix-socket "$CS_SOCK" -H 'Expect:' --data-binary @- http://hub/permission <<<"$input" &
pid=$!
trap 'kill "$pid" 2>/dev/null' TERM INT HUP   # Esc in Claude Code kills this hook: hang up on the hub
wait "$pid"
exit 0
