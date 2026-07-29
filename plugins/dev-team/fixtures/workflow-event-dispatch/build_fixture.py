"""Fixture builder for the workflow-worker / workflow-script `--event` dry-run harness.

Builds one of four named combinations: a throwaway git repo with an uncommitted change, plus a
throwaway workflow context file (following `use-context-file`'s section-sentinel format) whose
`Project Configuration` section carries a fictional `instructions` map keyed by the fictional
event `fizzle` — reusing the same fictional event and commit-producing/unrecognized-instruction
entry shapes as `plugins/dev-team/fixtures/run-event-hooks/build_fixture.py` (ADR-360), so this
harness proves the two callers' generic wrapping mechanics rather than testing today's specific
shipped defaults.

Two independent dimensions:
- `target`: which skill under test is being dry-run — "worker" (`workflow-worker`, wrapping the
  `get-project-configuration` skill) or "script" (`workflow-script`, wrapping a trivial command).
- `scenario`: "with-event" (passes `--event fizzle`, so both hooks should fire) or "no-event"
  (omits `--event` entirely, even though the same `instructions` map is present in the context
  file's Project Configuration section — proving the omission is what suppresses the hook calls,
  not merely the absence of configured instructions).

`with-event` sets `before-fizzle` to a commit-producing entry (proves the before-hook actually
ran: the repo's pre-existing uncommitted change gets committed) and the unconditional `after-fizzle`
key to an unrecognized instruction (proves the after-hook actually ran, and that its failure flips
the wrapping skill's own overall result even though the wrapped skill/command itself succeeds).
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EVENT = "fizzle"
TARGETS = ("worker", "script")
SCENARIOS = ("with-event", "no-event")

_INSTRUCTIONS_MAP = {
    "before-fizzle": {"commit-uncommitted": "Commit any uncommitted changes"},
    "after-fizzle": {"recite-hamlet": "Recite three lines from Hamlet"},
}


@dataclass
class DispatchFixture:
    """Everything a dry run of `workflow-worker`/`workflow-script` needs: the fixture git repo
    to observe, the throwaway context file carrying the fictional `instructions` map, which CLI
    arguments to invoke the target skill with, and the outcomes the harness expects."""

    worktree: Path
    context_file: Path
    target: str  # "worker" | "script"
    scenario: str  # "with-event" | "no-event"
    cli_args: str  # the full argument string to pass to the target skill
    expected_starting_commit_count: int
    expected_commit_count_after_run: int
    expected_overall_result_kind: str  # "successful" | "failed"
    grading_notes: str


def _run_git(args: list[str], cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _write_file(work: Path, relative_path: str, content: str) -> None:
    file_path = work / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)


def _init_repo_with_uncommitted_change(dest: Path) -> Path:
    """A throwaway git repo, one commit deep, with one further uncommitted change on top — the
    entry state every combination in this harness starts from."""
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


def _write_context_file(dest: Path) -> Path:
    """A minimal throwaway workflow context file, following `use-context-file`'s
    section-sentinel format, whose `Project Configuration` section supplies the fictional
    `instructions` map. Present in both scenarios' context files — only whether `--event` is
    passed on the CLI determines whether it is ever consulted."""
    context_file = dest / "fixture-context.md"
    project_config = {"instructions": _INSTRUCTIONS_MAP}
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


def _worker_cli_args(scenario: str, context_file: Path) -> str:
    args = (
        f"--context-file {context_file} --write-section \"Dry Run Output\" "
        f"--skill get-project-configuration"
    )
    if scenario == "with-event":
        args += f" --event {EVENT}"
    return args


def _script_cli_args(scenario: str, context_file: Path, dest: Path) -> str:
    log_file = dest / "script.log"
    command = "python3 -c \"print('Succeeded')\""
    args = (
        f"--context-file {context_file} --write-section \"Dry Run Result\" "
        f"--command '{command}' --log-file {log_file}"
    )
    if scenario == "with-event":
        args += f" --event {EVENT}"
    return args


def build_worker_scenario(scenario: str, dest: Path) -> DispatchFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(dest)
    cli_args = _worker_cli_args(scenario, context_file)
    if scenario == "with-event":
        return DispatchFixture(
            worktree=work,
            context_file=context_file,
            target="worker",
            scenario=scenario,
            cli_args=cli_args,
            expected_starting_commit_count=1,
            expected_commit_count_after_run=2,
            expected_overall_result_kind="failed",
            grading_notes=(
                "Commit count must become 2 (before-hook committed the pre-existing "
                "uncommitted README.md change) — proves the before-hook ran. The 'Dry Run "
                "Output' section must contain get-project-configuration's merged-config JSON "
                "— proves the wrapped skill ran. The overall returned result must be a failure "
                "description mentioning the unrecognized 'recite-hamlet'/Hamlet instruction — "
                "proves the after-hook ran and that its failure flips workflow-worker's own "
                "reported result even though the wrapped skill itself succeeded."
            ),
        )
    return DispatchFixture(
        worktree=work,
        context_file=context_file,
        target="worker",
        scenario=scenario,
        cli_args=cli_args,
        expected_starting_commit_count=1,
        expected_commit_count_after_run=1,
        expected_overall_result_kind="successful",
        grading_notes=(
            "Commit count must stay 1 (no hook fired despite the same `instructions` map "
            "being present in the context file) — proves omitting --event suppresses both "
            "hook calls entirely. The 'Dry Run Output' section must still contain "
            "get-project-configuration's output. The overall returned result must be "
            "'successful' — byte-for-byte identical to behavior before --event existed."
        ),
    )


def build_script_scenario(scenario: str, dest: Path) -> DispatchFixture:
    work = _init_repo_with_uncommitted_change(dest)
    context_file = _write_context_file(dest)
    cli_args = _script_cli_args(scenario, context_file, dest)
    if scenario == "with-event":
        return DispatchFixture(
            worktree=work,
            context_file=context_file,
            target="script",
            scenario=scenario,
            cli_args=cli_args,
            expected_starting_commit_count=1,
            expected_commit_count_after_run=2,
            expected_overall_result_kind="failed",
            grading_notes=(
                "Commit count must become 2 (before-hook committed the pre-existing "
                "uncommitted README.md change) — proves the before-hook ran. The 'Dry Run "
                "Result' section must contain 'Succeeded' and the log file path — proves the "
                "command ran and step 3's result parsing worked. The overall returned result "
                "must be a failure description mentioning the unrecognized instruction, even "
                "though the command itself printed 'Succeeded' — proves the after-hook's "
                "outcome is computed from the validation result (success, since the command "
                "printed 'Succeeded') independent of, and its failure still flips, "
                "workflow-script's own overall result."
            ),
        )
    return DispatchFixture(
        worktree=work,
        context_file=context_file,
        target="script",
        scenario=scenario,
        cli_args=cli_args,
        expected_starting_commit_count=1,
        expected_commit_count_after_run=1,
        expected_overall_result_kind="successful",
        grading_notes=(
            "Commit count must stay 1 (no hook fired despite the same `instructions` map "
            "being present in the context file) — proves omitting --event suppresses both "
            "hook calls entirely. The 'Dry Run Result' section must still contain 'Succeeded' "
            "and the log file path. The overall returned result must be 'successful' — "
            "byte-for-byte identical to behavior before --event existed."
        ),
    )


_BUILDERS = {
    "worker": build_worker_scenario,
    "script": build_script_scenario,
}


def build_fixture(target: str, scenario: str, dest: Path) -> DispatchFixture:
    if target not in TARGETS:
        raise ValueError(f"Unknown target {target!r}; expected one of {TARGETS}")
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}; expected one of {SCENARIOS}")
    dest.mkdir(parents=True, exist_ok=True)
    return _BUILDERS[target](scenario, dest)


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {Path(sys.argv[0]).name} <target> <scenario> <dest-dir>", file=sys.stderr)
        print(f"Targets: {', '.join(TARGETS)}", file=sys.stderr)
        print(f"Scenarios: {', '.join(SCENARIOS)}", file=sys.stderr)
        sys.exit(1)

    target, scenario, dest = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    try:
        fixture = build_fixture(target, scenario, dest)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"worktree: {fixture.worktree}")
    print(f"context_file: {fixture.context_file}")
    print(f"target: {fixture.target}")
    print(f"scenario: {fixture.scenario}")
    print(f"cli_args: {fixture.cli_args}")
    print(f"expected_starting_commit_count: {fixture.expected_starting_commit_count}")
    print(f"expected_commit_count_after_run: {fixture.expected_commit_count_after_run}")
    print(f"expected_overall_result_kind: {fixture.expected_overall_result_kind}")
    print(f"grading_notes: {fixture.grading_notes}")


if __name__ == "__main__":
    main()
