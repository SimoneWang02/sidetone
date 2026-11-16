# Shared TTS helpers for speak.sh and notify.sh (sourced, not executed).
# Engine order: macOS say -> Kokoro -> Piper -> spd-say -> espeak-ng.
TTS_PIDFILE="$HOME/.claude/hooks/.tts.pid"
KOKORO_DIR="${KOKORO_DIR:-$HOME/.local/share/kokoro}"
PIPER_DIR="${PIPER_DIR:-$HOME/.local/share/piper}"
PIPER_VOICE="${PIPER_VOICE:-$PIPER_DIR/voices/en_US-lessac-medium.onnx}"
export KOKORO_DIR KOKORO_VOICE="${KOKORO_VOICE:-af_heart}" KOKORO_SPEED="${KOKORO_SPEED:-1.1}"

tts_stop() {  # stop whatever the previous turn is still saying
  [ -f "$TTS_PIDFILE" ] || return 0
  local pid; pid=$(cat "$TTS_PIDFILE")
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null
  rm -f "$TTS_PIDFILE"
  command -v spd-say >/dev/null 2>&1 && spd-say -C >/dev/null 2>&1
  return 0
}

# Run a "synth | paplay" pipeline in its own process group so tts_stop can kill all of it.
_tts_pipe() {  # $1 = text, $2 = sample rate, rest = synth command (reads stdin, writes s16le)
  local text=$1 rate=$2; shift 2
  TTS_TEXT="$text" TTS_RATE="$rate" setsid bash -c \
    'printf "%s" "$TTS_TEXT" | "$@" 2>/dev/null | paplay --raw --rate="$TTS_RATE" --format=s16le --channels=1' \
    _ "$@" </dev/null >/dev/null 2>&1 &
}

tts_say() {  # $1 = text; speaks in the background and returns immediately
  tts_stop
  if command -v say >/dev/null 2>&1; then
    nohup say -r 210 <<<"$1" >/dev/null 2>&1 &
  elif command -v paplay >/dev/null 2>&1 && [ -x "$KOKORO_DIR/venv/bin/python" ] && [ -f "$KOKORO_DIR/kokoro-v1.0.onnx" ]; then
    _tts_pipe "$1" 24000 "$KOKORO_DIR/venv/bin/python" -I "$HOME/.claude/hooks/kokoro-say.py"
  elif command -v paplay >/dev/null 2>&1 && [ -x "$PIPER_DIR/piper/piper" ] && [ -f "$PIPER_VOICE" ]; then
    local rate; rate=$(jq -r '.audio.sample_rate // 22050' "$PIPER_VOICE.json" 2>/dev/null)
    _tts_pipe "$1" "${rate:-22050}" "$PIPER_DIR/piper/piper" --model "$PIPER_VOICE" --output-raw
  elif command -v spd-say >/dev/null 2>&1; then
    nohup spd-say -w -e <<<"$1" >/dev/null 2>&1 &
  elif command -v espeak-ng >/dev/null 2>&1; then
    nohup espeak-ng <<<"$1" >/dev/null 2>&1 &
  else
    return 0
  fi
  echo $! > "$TTS_PIDFILE"
}
