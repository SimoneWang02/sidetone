#!/usr/bin/env bash
# PreToolUse and PostToolUse: ends the turn when the hub was asked to stop this session (the
# cancel key, see Hub._stop_turn). The hub leaves a file named after the session in
# $CS_RUN/stop. With no such file there is nothing to do, and that is seen without reading the
# input, so a tool call is held up by no more than the start of this script.
. "${BASH_SOURCE[0]%/*}/lib.sh"
main() {
  local dir=$CS_RUN/stop session event told
  compgen -G "$dir/*" >/dev/null || exit 0
  IFS=$'\t' read -r session event < <(jq -r '[.session_id // "", .hook_event_name // ""] | @tsv' 2>/dev/null)
  case $session in ''|.*|*/*) exit 0 ;; esac
  rm "$dir/$session" 2>/dev/null || exit 0   # not this session, or another hook of it was first
  told='The user stopped this turn with the cancel key. Do not go on with it unless they ask.'
  if [ "$event" = PreToolUse ]; then   # this call is not made either
    jq -cn --arg told "$told" '{continue: false, stopReason: $told, hookSpecificOutput:
      {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $told}}'
  else
    jq -cn --arg told "$told" '{continue: false, stopReason: $told}'
  fi
}
main
