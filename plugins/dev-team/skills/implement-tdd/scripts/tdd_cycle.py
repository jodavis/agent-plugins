#!/usr/bin/env python3
"""Drive the tdd-tester / tdd-implementer / tdd-refactorer TDD loop for one Testable
component as isolated `claude` CLI subprocesses that never see each other's or the
caller's conversation — communication is limited to the turn messages this script
relays between them.

Usage:
  tdd_cycle.py --component-prompt <path> --component-name <name> --repo-root <path>
               --work-item-id <id> --state-file <path>
               [--answer "<clarify answer>"] [--resolved-directly]

Exit 0 with `{"status": "done", ...}` on stdout once the component is fully covered
and committed. Exit 1 with `{"status": "escalation", "recommended_action": ...}` when
the loop hits something it can't resolve itself (a Tier 2 escalation from
tdd-implementer, or a protocol violation) — the caller (Developer) resolves it and
re-invokes this script with the same --state-file to continue.

Confirmed by live smoke test (see PR/session notes) before this landed:
  1. `--agent dev-team:tdd-tester` (a plugin-scoped agent name) resolves correctly.
  2. `claude -p --output-format json` produces a JSON object with `session_id` and
     `result` keys, and `--resume <session_id>` reuses the same id and hits the prompt
     cache for prior turns — the "keep it warm" design this replaces the SendMessage
     approach for.
  3. `--permission-mode acceptEdits` alone auto-approves Edit/Write but silently denies
     Bash — Bash needs an explicit `--allowedTools "Bash(pytest*) Bash(git*) ..."`
     scoped allowlist (not `--permission-mode bypassPermissions`, which disables all
     per-action checks and is a real escalation, not something to reach for by
     default). `--allowedTools` is variadic and will swallow a positional prompt
     argument that follows it, so the prompt is passed on stdin instead, never as a
     trailing CLI argument.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

AGENT_NAMES = {
    "tester": "dev-team:tdd-tester",
    "implementer": "dev-team:tdd-implementer",
    "refactorer": "dev-team:tdd-refactorer",
}

DEFAULT_PERMISSION_MODE = "acceptEdits"
# Scoped allowlist so Bash doesn't need bypassPermissions — validated by live smoke
# test. Edit/Write/Read/Glob/Grep are included even though acceptEdits alone already
# covers Edit/Write, for a single explicit list rather than relying on default
# behavior for some tools and an allowlist for others.
ALLOWED_TOOLS = "Bash(pytest*) Bash(python3*) Bash(git*) Edit Write Read Glob Grep"

GENERIC_TESTER_TURN = "take your next turn for {component}."
IMPLEMENTER_TURN_TEMPLATE = "tdd-tester reported: {reply}."
REFACTORER_TURN_TEMPLATE = (
    "review {component} for duplication, brittle setup, or naive implementations "
    "left over from green turns. No behavior changes."
)

MAX_TURNS = 200


def _log(msg: str) -> None:
    """Turn-by-turn progress to stderr — inspectable in the background run's log file
    without generating a notification per line, unlike a Monitor-watched stream."""
    print(f"[tdd_cycle] {msg}", file=sys.stderr, flush=True)


class ClaudeCliError(RuntimeError):
    pass


class TddProtocolError(RuntimeError):
    """Raised when the loop exceeds MAX_TURNS — something is stuck."""


@dataclass
class TrioState:
    """Session IDs for the trio, persisted to the state file so the loop is resumable
    across separate script invocations (each `claude -p` call is a fresh process)."""

    tester_session: str | None = None
    implementer_session: str | None = None
    refactorer_session: str | None = None
    last_tester_reply: str | None = None

    @classmethod
    def load(cls, path: Path) -> "TrioState":
        if not path.exists():
            return cls()
        return cls(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


@dataclass
class DoneResult:
    coverage_summary: str
    commit_message: str


@dataclass
class EscalationResult:
    recommended_action: str
    reason: str
    state_file: str


# ---------------------------------------------------------------------------
# claude CLI invocation (the one impure boundary — see module docstring)
# ---------------------------------------------------------------------------


def run_claude_turn(
    *,
    message: str,
    agent: str | None,
    session_id: str | None,
    repo_root: Path,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
) -> tuple[str, str]:
    """Run one `claude -p` turn — a fresh session if `session_id` is None (requires
    `agent`), otherwise a resume of that session. Returns (session_id, result_text).
    Raises ClaudeCliError on a non-zero exit or unparseable output.

    The prompt is passed on stdin, not as a trailing CLI argument — `--allowedTools`
    is variadic and greedily consumes a positional prompt argument that follows it."""
    cmd = [
        "claude", "-p", "--output-format", "json", "--permission-mode", permission_mode,
        "--allowedTools", ALLOWED_TOOLS,
    ]
    if session_id:
        cmd += ["--resume", session_id]
    else:
        if not agent:
            raise ValueError("agent is required when starting a fresh session")
        cmd += ["--agent", agent]

    result = subprocess.run(cmd, cwd=repo_root, input=message, capture_output=True, text=True)
    if result.returncode != 0:
        raise ClaudeCliError(f"claude CLI exited {result.returncode}: {result.stderr.strip()}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeCliError(
            f"could not parse claude CLI JSON output: {e}\n{result.stdout[:500]}"
        ) from e

    new_session_id = payload.get("session_id") or session_id
    if not new_session_id:
        raise ClaudeCliError(f"claude CLI output had no session_id: {payload}")
    return new_session_id, payload.get("result", "")


# ---------------------------------------------------------------------------
# Reply classification (pure)
# ---------------------------------------------------------------------------

_REPLY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("structural_red", re.compile(r"^structural-red:\s*(.+)$")),
    ("red", re.compile(r"^red:\s*(.+)$")),
    ("done", re.compile(r"^done:\s*(.+)$")),
    ("structural_green", re.compile(r"^structural-green:\s*(.+)$")),
    ("green", re.compile(r"^green:\s*(.+)$")),
    ("revise_request", re.compile(r"^revise-request:\s*(.+)$")),
    ("escalate", re.compile(r"^escalate:\s*(.+?)\s*—\s*recommended_action:\s*(\w+)$")),
    ("refactored", re.compile(r"^refactored:\s*(.+)$")),
    ("no_refactor_needed", re.compile(r"^no-refactor-needed\b")),
]


def classify_reply(text: str) -> tuple[str, dict]:
    """Classify a trio member's reply by scanning every line for its one-line status
    marker. Trio members are instructed to lead with it, but in practice sometimes add
    prose before it or wrap it in a code fence — take the first line anywhere that
    matches rather than requiring it to be literally the first line. Returns (kind,
    details); kind is "unrecognized" if no line matches (details["raw"] is the first
    non-empty line, for a useful error message)."""
    first_line = ""
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if not first_line:
            first_line = line
        for kind, pattern in _REPLY_PATTERNS:
            m = pattern.match(line)
            if not m:
                continue
            if kind == "escalate":
                return kind, {"reason": m.group(1), "recommended_action": m.group(2)}
            groups = m.groups()
            return kind, {"detail": groups[0] if groups else ""}
    return "unrecognized", {"raw": first_line}


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def changed_files(repo_root: Path) -> list[str]:
    """Modified tracked files plus new untracked files — a trio member's first edit to
    a brand-new file is untracked, so `git diff --name-only` alone would miss it."""
    tracked = subprocess.run(
        ["git", "diff", "--name-only"], cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [p for p in (*tracked, *untracked) if p.strip()]


def is_test_file(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def stage(repo_root: Path, paths: list[str]) -> None:
    if not paths:
        return
    subprocess.run(["git", "add", *paths], cwd=repo_root, capture_output=True, text=True, check=True)


def discard_unstaged(repo_root: Path, paths: list[str]) -> None:
    """Revert unstaged changes to `paths` — `git checkout --` only works for tracked
    files, so a brand-new untracked file (e.g. one a trio member just created out of
    scope) is deleted directly instead."""
    if not paths:
        return
    untracked = set(
        subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    )
    tracked_paths = [p for p in paths if p not in untracked]
    if tracked_paths:
        subprocess.run(
            ["git", "checkout", "--", *tracked_paths],
            cwd=repo_root, capture_output=True, text=True, check=True,
        )
    for p in paths:
        if p in untracked:
            (repo_root / p).unlink(missing_ok=True)


def commit(repo_root: Path, work_item_id: str, component: str, coverage_summary: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo_root, capture_output=True, text=True, check=True)
    message = f"{work_item_id}: implement {component} via TDD ({coverage_summary.strip()})"
    subprocess.run(
        ["git", "commit", "-m", message], cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return message


# ---------------------------------------------------------------------------
# The cycle itself
# ---------------------------------------------------------------------------


def _send(
    role: str,
    turn_message: str,
    state: TrioState,
    session_field: str,
    component_prompt: str,
    repo_root: Path,
    send_turn=run_claude_turn,
) -> str:
    session_id = getattr(state, session_field)
    if session_id is None:
        message = f"{component_prompt}\n\n---\n\n{turn_message}"
        agent = AGENT_NAMES[role]
    else:
        message = turn_message
        agent = None
    new_session_id, text = send_turn(
        message=message, agent=agent, session_id=session_id, repo_root=repo_root,
    )
    setattr(state, session_field, new_session_id)
    return text


def _protocol_violation(reason: str, state: TrioState, state_path: Path) -> EscalationResult:
    state.save(state_path)
    return EscalationResult(
        recommended_action="protocol_violation", reason=reason, state_file=str(state_path),
    )


def _after_real_green(
    component: str, repo_root: Path, state: TrioState, state_path: Path, component_prompt: str, send_turn,
) -> EscalationResult | None:
    """Run the refactor turn after a real green. Returns None to continue the main
    loop, or an EscalationResult if the refactorer's reply is unrecognized."""
    text = _send(
        "refactorer", REFACTORER_TURN_TEMPLATE.format(component=component), state,
        "refactorer_session", component_prompt, repo_root, send_turn,
    )
    state.save(state_path)
    kind, _details = classify_reply(text)
    _log(f"refactorer -> {kind}")
    if kind not in ("refactored", "no_refactor_needed"):
        return _protocol_violation(f"tdd-refactorer replied unexpectedly: {text!r}", state, state_path)
    stage(repo_root, changed_files(repo_root))
    return None


def run_cycle(
    *,
    component: str,
    component_prompt: str,
    repo_root: Path,
    work_item_id: str,
    state: TrioState,
    state_path: Path,
    injected_answer: str | None = None,
    resolved_directly: bool = False,
    send_turn=run_claude_turn,
    max_turns: int = MAX_TURNS,
) -> DoneResult | EscalationResult:
    pending_implementer_reply: str | None = None

    if injected_answer is not None:
        if not state.last_tester_reply:
            raise ValueError("no pending tester reply to answer — state file is inconsistent")
        msg = f"tdd-tester reported: {state.last_tester_reply}. {injected_answer}."
        pending_implementer_reply = _send(
            "implementer", msg, state, "implementer_session", component_prompt, repo_root, send_turn,
        )
        state.save(state_path)
    elif resolved_directly:
        stage(repo_root, changed_files(repo_root))
        result = _after_real_green(component, repo_root, state, state_path, component_prompt, send_turn)
        if result is not None:
            return result

    for _ in range(max_turns):
        if pending_implementer_reply is None:
            tester_text = _send(
                "tester", GENERIC_TESTER_TURN.format(component=component), state,
                "tester_session", component_prompt, repo_root, send_turn,
            )
            state.save(state_path)
            kind, details = classify_reply(tester_text)
            _log(f"tester -> {kind}: {details.get('detail', details)}")

            if kind == "done":
                message = commit(repo_root, work_item_id, component, details["detail"])
                return DoneResult(coverage_summary=details["detail"], commit_message=message)

            if kind not in ("structural_red", "red"):
                return _protocol_violation(
                    f"tdd-tester replied unexpectedly: {tester_text!r}", state, state_path,
                )

            changed = changed_files(repo_root)
            non_test = [p for p in changed if not is_test_file(p)]
            if non_test:
                discard_unstaged(repo_root, non_test)
                return _protocol_violation(
                    f"tdd-tester touched non-test file(s): {non_test}", state, state_path,
                )
            stage(repo_root, changed)
            state.last_tester_reply = tester_text.strip()
            state.save(state_path)

            implementer_text = _send(
                "implementer", IMPLEMENTER_TURN_TEMPLATE.format(reply=tester_text.strip()), state,
                "implementer_session", component_prompt, repo_root, send_turn,
            )
            state.save(state_path)
        else:
            implementer_text = pending_implementer_reply
            pending_implementer_reply = None

        kind, details = classify_reply(implementer_text)
        _log(f"implementer -> {kind}: {details.get('detail', details)}")

        if kind == "revise_request":
            retry_tester_text = _send(
                "tester", f"tdd-implementer requests revision: {details['detail']}", state,
                "tester_session", component_prompt, repo_root, send_turn,
            )
            state.save(state_path)
            implementer_text = _send(
                "implementer", f"tdd-tester responded: {retry_tester_text.strip()}.", state,
                "implementer_session", component_prompt, repo_root, send_turn,
            )
            state.save(state_path)
            kind, details = classify_reply(implementer_text)
            if kind == "revise_request":
                return _protocol_violation(
                    "tdd-implementer issued a second revise-request after its one allowed retry",
                    state, state_path,
                )

        if kind == "escalate":
            state.save(state_path)
            return EscalationResult(
                recommended_action=details["recommended_action"],
                reason=details["reason"],
                state_file=str(state_path),
            )

        if kind not in ("structural_green", "green"):
            return _protocol_violation(
                f"tdd-implementer replied unexpectedly: {implementer_text!r}", state, state_path,
            )

        changed = changed_files(repo_root)
        non_production = [p for p in changed if is_test_file(p)]
        if non_production:
            discard_unstaged(repo_root, non_production)
            return _protocol_violation(
                f"tdd-implementer touched test file(s): {non_production}", state, state_path,
            )
        stage(repo_root, changed)

        if kind == "structural_green":
            continue

        result = _after_real_green(component, repo_root, state, state_path, component_prompt, send_turn)
        if result is not None:
            return result

    raise TddProtocolError(f"exceeded max_turns={max_turns} without reaching done — likely stuck")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-prompt", required=True)
    parser.add_argument("--component-name", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--work-item-id", required=True)
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--answer", default=None)
    parser.add_argument("--resolved-directly", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    state_path = Path(args.state_file)
    state = TrioState.load(state_path)
    component_prompt = Path(args.component_prompt).read_text(encoding="utf-8")

    try:
        result = run_cycle(
            component=args.component_name,
            component_prompt=component_prompt,
            repo_root=repo_root,
            work_item_id=args.work_item_id,
            state=state,
            state_path=state_path,
            injected_answer=args.answer,
            resolved_directly=args.resolved_directly,
        )
    except (ClaudeCliError, TddProtocolError) as e:
        print(json.dumps({"status": "error", "reason": str(e)}, indent=2))
        return 1

    if isinstance(result, DoneResult):
        print(json.dumps(
            {"status": "done", "commit_message": result.commit_message,
             "coverage_summary": result.coverage_summary},
            indent=2,
        ))
        return 0

    print(json.dumps(
        {"status": "escalation", "recommended_action": result.recommended_action,
         "reason": result.reason, "state_file": result.state_file},
        indent=2,
    ))
    return 1


if __name__ == "__main__":
    sys.exit(main())
