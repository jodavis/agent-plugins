"""Fixture builder for the run-event-hooks skill's dry-run harness.

Builds one of three named scenarios: a throwaway git repo with an uncommitted change, plus a
throwaway workflow context file (following `use-context-file`'s section-sentinel format) whose
`Project Configuration` section carries a fictional `instructions` map keyed by a fictional
event, `fizzle` — a fictional event/label is deliberate, per the spec's own scenario design, so
the harness proves the generic lookup-and-follow mechanism works rather than testing today's
specific shipped defaults. Each scenario uses a local commit (not a push) as its observable
action, so no fixture remote is needed.

Scenarios:
- "commit-entry": one commit-producing instruction ("Commit any uncommitted changes") run
  against a repo with uncommitted changes — the skill should create a new local commit and
  report "completed".
- "disabled-entry": the same instruction overridden to "" (disabled) — the skill should create
  no new commit and still report "completed" (a no-op is not a failure).
- "unrecognized-instruction": one genuinely unrecognized instruction ("Recite three lines from
  Hamlet") with no plausible matching operation — the skill must attempt it rather than
  silently no-op'ing, and report "failed" since nothing actually fits.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EVENT = "fizzle"
PHASE = "before"

SCENARIOS = ("commit-entry", "disabled-entry", "unrecognized-instruction")


@dataclass
class ScenarioFixture:
    """Everything a dry run of `run-event-hooks` needs: the fixture git repo the instruction
    should act on, the throwaway context file carrying the fictional `instructions` map, which
    event/phase to pass the skill, and the outcomes the harness expects: the skill's own
    "completed"/"failed" return value, and whether a new local commit should exist afterward."""

    worktree: Path
    context_file: Path
    event: str
    phase: str
    expected_outcome: str  # "completed" | "failed" -- run-event-hooks's own return value
    expected_commit_created: bool  # mechanical check: did a new local commit appear?


def _run_git(args: list[str], cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_repo_with_uncommitted_change(dest: Path) -> Path:
    """A throwaway git repo, one commit deep, with one further uncommitted change on top —
    the entry state every scenario in this harness starts from."""
    work = dest / "work"
    work.mkdir(parents=True, exist_ok=True)
    _run_git(["init"], cwd=work)
    _run_git(["config", "user.email", "fixture@example.com"], cwd=work)
    _run_git(["config", "user.name", "Fixture"], cwd=work)
    _write_file(work, "README.md", "initial\n")
    _run_git(["add", "README.md"], cwd=work)
    _run_git(["commit", "-m", "initial commit"], cwd=work)
    _write_file(work, "README.md", "initial\nuncommitted change\n")
    return work


def _write_file(work: Path, relative_path: str, content: str) -> None:
    file_path = work / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)


def _write_context_file(dest: Path, instructions_entries: dict) -> Path:
    """A minimal throwaway workflow context file, following `use-context-file`'s
    section-sentinel format, whose `Project Configuration` section supplies the fictional
    `instructions` map the skill under test should read."""
    context_file = dest / "fixture-context.md"
    project_config = {"instructions": {f"{PHASE}-{EVENT}": instructions_entries}}
    body = (
        "---\n"
        "work_item_id: FIZZLE-1\n"
        "spec_path: \n"
        "state: implementing\n"
        "---\n\n"
        "# FIZZLE-1 Dev Team Context\n\n"
        "<!-- section:Project Configuration -->\n\n"
        f"{json.dumps(project_config, indent=2)}\n"
    )
    context_file.write_text(body)
    return context_file


def build_commit_entry_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(
        dest, {"commit-uncommitted": "Commit any uncommitted changes"}
    )
    return ScenarioFixture(work, context_file, EVENT, PHASE, "completed", True)


def build_disabled_entry_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(dest, {"commit-uncommitted": ""})
    return ScenarioFixture(work, context_file, EVENT, PHASE, "completed", False)


def build_unrecognized_instruction_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(
        dest, {"recite-hamlet": "Recite three lines from Hamlet"}
    )
    return ScenarioFixture(work, context_file, EVENT, PHASE, "failed", False)


_BUILDERS = {
    "commit-entry": build_commit_entry_scenario,
    "disabled-entry": build_disabled_entry_scenario,
    "unrecognized-instruction": build_unrecognized_instruction_scenario,
}


def build_scenario(name: str, dest: Path) -> ScenarioFixture:
    if name not in _BUILDERS:
        raise ValueError(f"Unknown scenario {name!r}; expected one of {SCENARIOS}")
    dest.mkdir(parents=True, exist_ok=True)
    return _BUILDERS[name](dest)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} <scenario> <dest-dir>", file=sys.stderr)
        print(f"Scenarios: {', '.join(SCENARIOS)}", file=sys.stderr)
        sys.exit(1)

    scenario, dest = sys.argv[1], Path(sys.argv[2])
    try:
        fixture = build_scenario(scenario, dest)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"worktree: {fixture.worktree}")
    print(f"context_file: {fixture.context_file}")
    print(f"event: {fixture.event}")
    print(f"phase: {fixture.phase}")
    print(f"expected_outcome: {fixture.expected_outcome}")
    print(f"expected_commit_created: {fixture.expected_commit_created}")


if __name__ == "__main__":
    main()
