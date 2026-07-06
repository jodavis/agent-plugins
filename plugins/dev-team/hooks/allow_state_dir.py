#!/usr/bin/env python3
"""PreToolUse hook: auto-allow Read/Write/Edit/Bash/Monitor calls scoped to the
dev-team plugin's own state directory.

The dev-team pipeline constantly reads and writes context files, todo logs, and
build/validation logs under <DEV_TEAM_STATE_DIR or ~/.dev-team>. That directory is
owned entirely by this plugin, so tool calls confined to it are always safe to
auto-approve rather than prompting the user on every step.

Reads the PreToolUse hook payload from stdin (see Claude Code hooks docs for the
schema) and prints an "allow" decision when the call is scoped to the state dir.
Prints nothing and exits 0 otherwise, deferring to the normal permission flow.
Never blocks or denies — a parse error or unrecognized tool is treated the same
as "not in scope," not "not allowed."
"""

import json
import os
import sys
from pathlib import Path

_PATH_FIELD_TOOLS = {"Read", "Write", "Edit"}
_COMMAND_FIELD_TOOLS = {"Bash", "Monitor"}


def _state_dir() -> Path:
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    base = Path(base_env) if base_env else Path.home() / ".dev-team"
    return base.expanduser().resolve()


def _allow() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "scoped to the dev-team plugin's own state directory",
        }
    }))


def _is_in_state_dir(path_str: str, state_dir: Path) -> bool:
    try:
        candidate = Path(path_str).expanduser().resolve()
    except (OSError, ValueError):
        return False
    return candidate == state_dir or state_dir in candidate.parents


def _command_targets_state_dir(command: str, state_dir: Path) -> bool:
    # Bash/Monitor commands reference the directory as a substring (e.g. inside a
    # larger pipeline), so an exact-path check doesn't apply — look for the
    # resolved path, plus common unexpanded forms, as substrings instead.
    needles = [str(state_dir), "$DEV_TEAM_STATE_DIR", "${DEV_TEAM_STATE_DIR}"]
    home = str(Path.home())
    if str(state_dir).startswith(home):
        needles.append("~" + str(state_dir)[len(home):])
    return any(needle in command for needle in needles)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    state_dir = _state_dir()

    if tool_name in _PATH_FIELD_TOOLS:
        file_path = tool_input.get("file_path", "")
        if file_path and _is_in_state_dir(file_path, state_dir):
            _allow()
    elif tool_name in _COMMAND_FIELD_TOOLS:
        command = tool_input.get("command", "")
        if command and _command_targets_state_dir(command, state_dir):
            _allow()


if __name__ == "__main__":
    main()
