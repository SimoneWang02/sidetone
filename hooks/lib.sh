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

# A hub is there to talk to: its Unix socket, or the port and token of one on a local port.
hub_up() { [ -S "$CS_SOCK" ] || [ -s "$CS_RUN/hub.addr" ]; }

# How to reach the hub, for curl: HUB (its arguments) and HUB_URL. The Unix socket, or else a
# hub on a local port (Windows, or SIDETONE_TRANSPORT=tcp) with the port and token in hub.addr.
hub_door() {
  if [ -S "$CS_SOCK" ]; then HUB=(--unix-socket "$CS_SOCK"); HUB_URL=http://hub; return 0; fi
  local port token
  read -r port token 2>/dev/null <"$CS_RUN/hub.addr" || return 1
  HUB=(-H "X-Sidetone-Token: $token"); HUB_URL=http://127.0.0.1:$port
}

# POST stdin to the hub and print its reply. $1 = path, $2 = max seconds (default 1).
# Fails fast when the hub is not running, so callers can fall back.
hub_post() {
  hub_door || return 1
  curl -sf -m "${2:-1}" "${HUB[@]}" -H 'Expect:' --data-binary @- "$HUB_URL$1"
}

# Start the hub in the background and return at once. A second hub exits by itself (it takes a lock).
hub_start() {
  local py=$KOKORO_DIR/venv/bin/python
  [ -x "$py" ] || py=$(command -v python3) || return 1   # no Kokoro: the hub uses a system voice
  [ -f "$CS_ROOT/hub/hub.py" ] || return 1
  mkdir -p "$CS_RUN" "$CS_STATE" && chmod 700 "$CS_RUN" || return 1
  # In a session of its own, so it outlives the hook that started it. A Mac has no setsid
  # command: perl, which every Mac has, does the same call (forking first, as setsid does, when
  # it already leads a process group, which cannot start a session).
  local own=(setsid)
  command -v setsid >/dev/null 2>&1 ||
    own=(perl -MPOSIX -e 'if (getpgrp() == $$) { exit 0 if fork() } POSIX::setsid() or die "setsid: $!"; exec @ARGV or die "$!"' --)
  CS_RUN=$CS_RUN CS_STATE=$CS_STATE KOKORO_DIR=$KOKORO_DIR \
    "${own[@]}" nohup "$py" -I "$CS_ROOT/hub/hub.py" </dev/null >>"$CS_STATE/hub.log" 2>&1 &
}
