#!/usr/bin/env bash
# Background listener (asyncRewake hook on Stop and SessionStart): waits on the hub for a spoken
# follow-up addressed to this session. When one arrives it is printed for Claude and the hook
# exits 2, which wakes the session even if it is idle. A newer listener or the session ending
# makes the hub release this one, and it exits quietly. If the hub restarts, it reconnects.
input=$(cat)
. "${BASH_SOURCE[0]%/*}/lib.sh"
[ -S "$CS_SOCK" ] || exit 0
reply=$(mktemp "$CS_RUN/listen.XXXXXX") || exit 0
pid=
trap '[ -n "$pid" ] && kill "$pid" 2>/dev/null; rm -f "$reply"; exit 0' TERM INT HUP
while :; do
  curl -sf -m 86400 --unix-socket "$CS_SOCK" -H 'Expect:' --data-binary @- http://hub/listen <<<"$input" >"$reply" &
  pid=$!
  wait "$pid" && break   # the hub answered: a follow-up, or "you are released"
  sleep "${CS_RETRY:-5}" & pid=$!   # the hub went away; an idle session should be reachable again once it is back
  wait "$pid"
done
text=$(jq -r '.text // empty' "$reply" 2>/dev/null)
rm -f "$reply"
[ -n "$text" ] || exit 0
cat >&2 <<MSG
The user said this by voice (push-to-talk, transcribed by a local speech model, so a word may be slightly off): "$text"
Treat it as their next message: act on it, and reply as usual, starting with the spoken line.
MSG
exit 2
