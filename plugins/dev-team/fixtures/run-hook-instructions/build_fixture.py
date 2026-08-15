"""Fixture builder for the run-hook-instructions skill's dry-run harness.

Builds one of two named scenarios: a throwaway git repo with an uncommitted change, plus a
throwaway workflow context file (following `use-context-file`'s section-sentinel format) and an
already-resolved, bare list of instruction strings to pass directly as `--instructions` —
dev_team.py resolves config, applies the per-label disable convention, and strips labels down to
a bare list before ever spawning the agent that calls this skill, so there is no "disabled entry"
scenario to build here; that filtering is covered at the dev_team.py level
(`test_dev_team.py::TestHookPhaseGating::test_disabled_entry_is_filtered_out`), not this skill's.
Each scenario uses a local commit (not a push) as its observable action, so no fixture remote is
needed.

Scenarios:
- "commit-entry": one commit-producing instruction ("Commit any uncommitted changes") run
  against a repo with uncommitted changes — the skill should create a new local commit and
  return "successful".
- "unrecognized-instruction": one genuinely unrecognized instruction ("Recite three lines from
  Hamlet") with no plausible matching operation — the skill must attempt it rather than
  silently no-op'ing, and its return must not be "successful" since nothing actually fits.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCENARIOS = ("commit-entry", "unrecognized-instruction")


@dataclass
class ScenarioFixture:
    """Everything a dry run of `run-hook-instructions` needs: the fixture git repo the
    instruction should act on, the throwaway context file, the already-resolved list of
    instruction strings to pass via `--instructions`, and the outcomes the harness expects:
    whether the skill's own return value is "successful", and whether a new local commit
    should exist afterward."""

    worktree: Path
    context_file: Path
    instructions: list
    expected_outcome: str  # "successful" | "failed" -- categorical, not the literal return text
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


def _write_context_file(dest: Path) -> Path:
    """A minimal throwaway workflow context file, following `use-context-file`'s
    section-sentinel format. None of this harness's scenarios need a field out of it (no
    pr_url/work_item_id-driven instruction), but --context-file is still a required argument."""
    context_file = dest / "fixture-context.md"
    body = (
        "---\n"
        "work_item_id: FIZZLE-1\n"
        "spec_path: \n"
        "state: implementing\n"
        "---\n\n"
        "# FIZZLE-1 Dev Team Context\n"
    )
    context_file.write_text(body)
    return context_file


def build_commit_entry_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(dest)
    instructions = ["Commit any uncommitted changes"]
    return ScenarioFixture(work, context_file, instructions, "successful", True)


def build_unrecognized_instruction_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(dest)
    instructions = ["Recite three lines from Hamlet"]
    return ScenarioFixture(work, context_file, instructions, "failed", False)


_BUILDERS = {
    "commit-entry": build_commit_entry_scenario,
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
    print(f"instructions: {json.dumps(fixture.instructions)}")
    print(f"expected_outcome: {fixture.expected_outcome}")
    print(f"expected_commit_created: {fixture.expected_commit_created}")


if __name__ == "__main__":
    main()
