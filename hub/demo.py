"""A scripted run of three made-up sessions, to see and hear every state without real work."""
from __future__ import annotations

import time

A, B, C = "demo-api", "demo-web", "demo-data"
CWD = {A: "/demo/api-server", B: "/demo/web-app", C: "/demo/data-pipeline"}


PROMPT = {A: "Fix the flaky login test", B: "Dark mode for the settings page", C: "Push the nightly export job"}


def _ev(event: str, sid: str, **extra) -> dict:
    if event == "UserPromptSubmit":
        extra.setdefault("prompt", PROMPT[sid])
    return {"hook_event_name": event, "session_id": sid, "cwd": CWD[sid], **extra}


def _tool(sid: str, name: str, **tool_input) -> dict:
    return _ev("PreToolUse", sid, tool_name=name, tool_input=tool_input)


def _speak(sid: str, text: str) -> dict:
    return _ev("MessageDisplay", sid, delta=f"<speak>{text}</speak>\n")


# (seconds to wait first, payload)
STEPS = [
    (0.0, _ev("SessionStart", A)), (0.0, _ev("SessionStart", B)), (0.0, _ev("SessionStart", C)),
    (1.0, _ev("UserPromptSubmit", A)), (0.5, _ev("UserPromptSubmit", B)), (0.5, _ev("UserPromptSubmit", C)),
    (1.0, _tool(A, "Bash", command="npm test", description="Running the tests")),
    (0.5, _ev("TaskCreated", B, task_id="1")), (0.0, _ev("TaskCreated", B, task_id="2")),
    (0.0, _ev("TaskCreated", B, task_id="3")),
    (1.0, _tool(B, "Edit", file_path="/demo/web-app/src/login.tsx")),
    (2.0, _ev("TaskCompleted", B, task_id="1")),
    (1.0, _tool(C, "Bash", command="git push", description="Pushing to the remote")),
    (1.0, _ev("Notification", C, notification_type="permission_prompt")),
    (5.0, _ev("PostToolUse", C, tool_name="Bash")),
    (1.0, _speak(A, "All forty two tests pass.")),
    (0.5, _ev("Stop", A, last_assistant_message="<speak>All forty two tests pass.</speak>")),
    (4.0, _ev("TaskCompleted", B, task_id="2")), (1.5, _ev("TaskCompleted", B, task_id="3")),
    (0.5, _speak(B, "The login page is fixed and ready for review.")),
    (0.5, _ev("Stop", B, last_assistant_message="<speak>The login page is fixed and ready for review.</speak>")),
    (5.0, _ev("StopFailure", C, error="rate_limit")),
    (8.0, _ev("SessionEnd", A)), (0.0, _ev("SessionEnd", B)), (0.0, _ev("SessionEnd", C)),
]


def run(hub, speed: float = 1.0) -> None:
    for delay, payload in STEPS:
        time.sleep(delay / speed)
        if payload["hook_event_name"] == "MessageDisplay":
            hub.on_display(payload)
        else:
            hub.on_event(payload)
