#!/usr/bin/env bash
# Stop hook (fallback): speaks the <speak> line if display.sh didn't already speak it.
[ -e "$HOME/.claude/voice-off" ] && exit 0
LOG="$HOME/.claude/hooks/voice.log"
input=$(cat)

speak_from() {  # prefer the last line that is exactly a <speak> tag; else the last tag anywhere
  local t; t=$(cat)
  local s; s=$(printf '%s\n' "$t" | grep -E '^[[:space:]]*<speak>.*</speak>[[:space:]]*$' | tail -n 1 |
    sed 's/^[[:space:]]*<speak>[[:space:]]*//; s/[[:space:]]*<\/speak>[[:space:]]*$//')
  [ -n "$s" ] || s=$(printf '%s' "$t" | tr '\r\n' '  ' | sed -n 's/.*<speak>\(.*\)<\/speak>.*/\1/p' |
    sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
  printf '%s' "$s"
}

(
  . "$HOME/.claude/hooks/tts-lib.sh"
  session=$(jq -r '.session_id // "unknown"' <<<"$input")
  transcript=$(jq -r '.transcript_path // empty' <<<"$input")
  speech=""

  # Use the final message from the payload when Claude Code provides it.
  msg=$(jq -r '.last_assistant_message // empty | if type == "string" then . else tostring end' <<<"$input" 2>/dev/null)
  [ -n "$msg" ] && speech=$(printf '%s' "$msg" | speak_from) && src=payload

  # Older versions: read the transcript, waiting up to ~3s for the final reply to land.
  if [ -z "$speech" ] && [ -f "$transcript" ]; then
    src=transcript
    for _ in $(seq 30); do
      last=$(tail -n 40 "$transcript" | jq -c 'select(.type == "user" or .type == "assistant")' 2>/dev/null | tail -n 1)
      if jq -e '.type == "assistant" and ([.message.content[]? | select(.type == "text")] | length > 0)' <<<"$last" >/dev/null 2>&1; then
        speech=$(jq -r '[.message.content[]? | select(.type == "text") | .text] | join("\n")' <<<"$last" | speak_from)
        break
      fi
      sleep 0.1
    done
  fi

  # Skip if the streaming hook already said this.
  spoken="$HOME/.claude/hooks/.state/$session.spoken"
  if [ -n "$speech" ] && [ -f "$spoken" ] && [ "$(cat "$spoken")" = "$speech" ]; then
    src="$src(already-spoken)"; rm -f "$spoken"; speech_to_say=""
  else
    rm -f "$spoken"; speech_to_say=$speech
  fi

  echo "$(date '+%F %T') [${session:0:8}] src=${src:-none} speech=${speech:-<none>}" >> "$LOG"
  [ -n "$speech_to_say" ] && tts_say "$speech_to_say"
) </dev/null >/dev/null 2>&1 &
exit 0
