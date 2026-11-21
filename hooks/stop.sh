#!/usr/bin/env bash
# PreToolUse and PostToolUse: ends the turn when the hub was asked to stop this session (the
# cancel key, see Hub._stop_turn). The hub leaves a file named after the session in
# $CS_RUN/stop. With no such file there is nothing to do, and that is seen without reading the
# input, so a tool call is held up by no more than the start of this script.
# After a step (PostToolUse) it also hands Claude the words spoken to it while it works, which
# the hub leaves in $CS_RUN/steer (Hub._leave_for_step): they go in as context for its next
# step, as a message typed while Claude works does. The file is taken by renaming it, as the
# hub takes it back, so only one of them has it.
. "${BASH_SOURCE[0]%/*}/lib.sh"
main() {
  local dir=$CS_RUN/stop steer=$CS_RUN/steer session event told
  compgen -G "$dir/*" >/dev/null || compgen -G "$steer/*" >/dev/null || exit 0
  IFS=$'\t' read -r session event < <(jq -r '[.session_id // "", .hook_event_name // ""] | @tsv' 2>/dev/null)
  case $session in ''|.*|*/*) exit 0 ;; esac
  if rm "$dir/$session" 2>/dev/null; then   # else not this session, or another hook of it was first
    told='The user stopped this turn with the cancel key. Do not go on with it unless they ask.'
    if [ "$event" = PreToolUse ]; then   # this call is not made either
      jq -cn --arg told "$told" '{continue: false, stopReason: $told, hookSpecificOutput:
        {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $told}}'
    else
      jq -cn --arg told "$told" '{continue: false, stopReason: $told}'
    fi
    exit 0
  fi
  [ "$event" = PostToolUse ] || exit 0
  mv "$steer/$session" "$steer/.$session.$$" 2>/dev/null || exit 0
  told=$(cat "$steer/.$session.$$"); rm -f "$steer/.$session.$$"
  [ -n "$told" ] || exit 0
  jq -cn --arg told "$told" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $told}}'
}
main
