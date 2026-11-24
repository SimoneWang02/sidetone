#!/usr/bin/env bash
# MessageDisplay hook: runs on each batch of streamed lines. When a line that is
# exactly <speak>...</speak> appears, speak it right away and show it as "🔊 ...".
# The tag may carry the session's title and the line's language (<speak title="..." lang="it">);
# the hub keeps them, and they are not shown.
# Must be fast: Claude Code waits for this hook before rendering the batch.
# Muted, the line is still rewritten: a session keeps writing the tag after the mute key stops
# the reminder (the author saw the raw tag, 2026-11-24), and the hub shows it at the session's
# light instead of saying it.
input=$(cat)
case $input in *'<speak'*) ;; *) exit 0 ;; esac   # fast path: nothing to do
. "${BASH_SOURCE[0]%/*}/lib.sh"

# The hub parses the batch, queues the speech (or shows it, muted) and returns the display rewrite.
if out=$(hub_post /display <<<"$input"); then
  [ -n "$out" ] && printf '%s\n' "$out"
  exit 0
fi

# No hub: start one for next time, and speak this line directly.
hub_start
out=$(jq -c '
  def tag: "^\\s*<speak(\\s+[A-Za-z]+\\s*=\\s*(\"[^\"]*\"|\u0027[^\u0027]*\u0027))*\\s*>\\s*(?<t>.*?)\\s*</speak>\\s*$";
  (.delta // "" | split("\n")) as $lines
  | { session: .session_id,
      speech: [ $lines[] | select(test(tag)) | sub(tag; "\(.t)") ] | last,
      display: ($lines | map(if test(tag) then sub(tag; "🔊 \(.t)") else . end) | join("\n")) }' <<<"$input") || exit 0

speech=$(jq -r '.speech // empty' <<<"$out")
[ -n "$speech" ] || exit 0

if voice_off; then   # muted: only the rewrite
  jq -c '{hookSpecificOutput: {hookEventName: "MessageDisplay", displayContent: .display}}' <<<"$out"
  exit 0
fi
session=$(jq -r '.session // "unknown"' <<<"$out")
mkdir -p "$CS_STATE/.state"
printf '%s' "$speech" > "$CS_STATE/.state/$session.spoken"   # lets the Stop hook (or the hub) skip a repeat
. "$CS_ROOT/hooks/tts-lib.sh"
tts_say "$speech"
echo "$(date '+%F %T') [${session:0:8}] src=stream(no-hub) speech=$speech" >> "$CS_STATE/voice.log"

jq -c '{hookSpecificOutput: {hookEventName: "MessageDisplay", displayContent: .display}}' <<<"$out"
