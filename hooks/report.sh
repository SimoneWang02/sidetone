#!/usr/bin/env bash
# Forwards a hook payload to the hub so it can track what the session is doing. Says nothing itself.
# With --start (SessionStart, UserPromptSubmit) it also starts the hub when it isn't running.
input=$(cat)
. "${BASH_SOURCE[0]%/*}/lib.sh"
hub_post /event <<<"$input" >/dev/null 2>&1 && exit 0
[ "${1:-}" = --start ] || exit 0
hub_start || exit 0
for _ in $(seq 50); do  # the hub needs a moment to bind its socket; then deliver this event
  sleep 0.1
  hub_post /event <<<"$input" >/dev/null 2>&1 && break
done
exit 0
