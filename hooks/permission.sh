#!/usr/bin/env bash
# PermissionRequest hook: offers the prompt to the hub, which can answer it from a hotkey while
# Claude Code's own dialog stays usable (whichever answers first wins). Prints the hub's decision,
# or nothing when the prompt was answered in the terminal. Without a hub, does nothing.
# One function called on the last line, so that editing this file while a prompt is open cannot
# make the waiting hook read on in the middle of the new text (see listen.sh).
main() {
  input=$(cat)
  . "${BASH_SOURCE[0]%/*}/lib.sh"
  hub_door || exit 0
  curl -sf -m 3600 "${HUB[@]}" -H 'Expect:' --data-binary @- "$HUB_URL/permission" <<<"$input" &
  pid=$!
  trap 'kill "$pid" 2>/dev/null' TERM INT HUP   # Esc in Claude Code kills this hook: hang up on the hub
  wait "$pid"
  exit 0
}
main; exit 0
