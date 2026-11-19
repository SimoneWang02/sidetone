# Shared paths and hub client for the hooks (sourced, not executed).
# The hub (hub/hub.py) does the speaking when it is running; every hook can also work without it.
CS_ROOT=${CS_ROOT:-$(cd "${BASH_SOURCE[0]%/*}/.." && pwd)}
if [ -z "${CS_RUN:-}" ]; then
  if [ -n "${XDG_RUNTIME_DIR:-}" ]; then CS_RUN=$XDG_RUNTIME_DIR/sidetone; else CS_RUN=/tmp/sidetone-$UID; fi
fi
CS_STATE=${CS_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/sidetone}
CS_SOCK=$CS_RUN/hub.sock
KOKORO_DIR=${KOKORO_DIR:-$HOME/.local/share/kokoro}

voice_off() { [ -e "$HOME/.claude/voice-off" ]; }

# POST stdin to the hub and print its reply. $1 = path, $2 = max seconds (default 1).
# Fails fast when the hub is not running, so callers can fall back.
hub_post() {
  [ -S "$CS_SOCK" ] || return 1
  curl -sf -m "${2:-1}" --unix-socket "$CS_SOCK" -H 'Expect:' --data-binary @- "http://hub$1"
}

# Start the hub in the background and return at once. A second hub exits by itself (it takes a lock).
hub_start() {
  local py=$KOKORO_DIR/venv/bin/python
  [ -x "$py" ] || py=$(command -v python3) || return 1   # no Kokoro: the hub uses a system voice
  [ -f "$CS_ROOT/hub/hub.py" ] || return 1
  mkdir -p "$CS_RUN" "$CS_STATE" && chmod 700 "$CS_RUN" || return 1
  CS_RUN=$CS_RUN CS_STATE=$CS_STATE KOKORO_DIR=$KOKORO_DIR \
    setsid nohup "$py" -I "$CS_ROOT/hub/hub.py" </dev/null >>"$CS_STATE/hub.log" 2>&1 &
}
