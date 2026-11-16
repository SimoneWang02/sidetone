#!/usr/bin/env bash
# MessageDisplay hook: runs on each batch of streamed lines. When a line that is
# exactly <speak>...</speak> appears, speak it right away and show it as "🔊 ...".
# Must be fast: Claude Code waits for this hook before rendering the batch.
[ -e "$HOME/.claude/voice-off" ] && exit 0
input=$(cat)
case $input in *'<speak>'*) ;; *) exit 0 ;; esac   # fast path: nothing to do

out=$(jq -c '
  def tag: "^\\s*<speak>\\s*(?<t>.*?)\\s*</speak>\\s*$";
  (.delta // "" | split("\n")) as $lines
  | { session: .session_id,
      speech: [ $lines[] | select(test(tag)) | sub(tag; "\(.t)") ] | last,
      display: ($lines | map(if test(tag) then sub(tag; "🔊 \(.t)") else . end) | join("\n")) }' <<<"$input") || exit 0

speech=$(jq -r '.speech // empty' <<<"$out")
[ -n "$speech" ] || exit 0

session=$(jq -r '.session // "unknown"' <<<"$out")
STATE="$HOME/.claude/hooks/.state"; mkdir -p "$STATE"
printf '%s' "$speech" > "$STATE/$session.spoken"   # lets the Stop hook skip a repeat
. "$HOME/.claude/hooks/tts-lib.sh"
tts_say "$speech"
echo "$(date '+%F %T') [${session:0:8}] src=stream speech=$speech" >> "$HOME/.claude/hooks/voice.log"

jq -c '{hookSpecificOutput: {hookEventName: "MessageDisplay", displayContent: .display}}' <<<"$out"
