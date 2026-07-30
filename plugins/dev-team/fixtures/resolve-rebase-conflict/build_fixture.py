"""Fixture builder for the resolve-rebase-conflict skill's dry-run harness.

Builds one of three named scenarios into a fresh working git clone, left mid-rebase with a
real conflict already in progress — the exact entry state `resolve-rebase-conflict` expects
(the state `rebase_onto()` leaves behind the moment it detects a conflict; see
`plugins/dev-team/skills/workflow-orchestrate/scripts/rebase_mechanic.py`).

Reuses `rebase_mechanic.rebase_onto()` itself to produce the conflict, and
`test_rebase_mechanic.py`'s bare-"origin"-plus-working-clone, diverge-then-rebase construction
approach — so each scenario's conflict state comes from a real rebase attempt against real git
subprocess calls, not hand-crafted conflict markers.

Scenarios:
- "single-file": one file (CHANGELOG.md), one conflicting hunk, resolvable purely from the
  scenario's task-brief text (append this task's own changelog entry alongside the one already
  merged upstream).
- "multi-file": two files conflict in the same rebase — the same CHANGELOG.md hunk as
  "single-file", plus a JSON settings file where this task's own change (bump `max_retries`)
  and an unrelated upstream change (bump `timeout_seconds`) land close enough together to
  conflict, but both remain resolvable from the scenario's task-brief text.
- "unresolvable": a single numeric setting that both branches changed to different, plausible
  values, where the task-brief text describes only the *intent* ("adjust the retry backoff
  multiplier for better resilience") and never states the target value — nothing in context
  tells a resolver which value (or a third one) is actually correct.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REBASE_MECHANIC_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "workflow-orchestrate"
    / "scripts"
)
sys.path.insert(0, str(_REBASE_MECHANIC_DIR))
from rebase_mechanic import rebase_onto  # noqa: E402

SCENARIOS = ("single-file", "multi-file", "unresolvable")

WORKING_BRANCH = "feature-branch"
BASE_BRANCH = "main"


@dataclass
class ScenarioFixture:
    """Everything a dry run of `resolve-rebase-conflict` needs: the worktree the rebase
    conflict was left in, which branches are involved, the task-brief text to hand the skill
    as its context argument, and the outcome the harness expects the skill to report."""

    worktree: Path
    working_branch: str
    base_branch: str
    task_brief: str
    expected_outcome: str  # "resolved" | "unresolved"


def _run_git(args: list[str], cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_repo_pair(dest: Path) -> Path:
    """Build a bare 'origin' repo and a working clone, both starting empty. Returns the
    working clone's path; the caller commits the shared initial state into it next."""
    origin = dest / "origin.git"
    _run_git(["init", "--bare", str(origin)], cwd=dest)

    work = dest / "work"
    _run_git(["clone", str(origin), str(work)], cwd=dest)
    return work


def _write_file(work: Path, relative_path: str, content: str) -> None:
    file_path = work / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)


def _commit_file(work: Path, relative_path: str, content: str, message: str) -> None:
    _write_file(work, relative_path, content)
    _run_git(["add", relative_path], cwd=work)
    _run_git(["commit", "-m", message], cwd=work)


def _commit_files(work: Path, files: dict[str, str], message: str) -> None:
    """Commit multiple files together, so a rebase that later conflicts on this commit
    conflicts on all of them at once rather than stopping at the first one replayed."""
    for relative_path, content in files.items():
        _write_file(work, relative_path, content)
        _run_git(["add", relative_path], cwd=work)
    _run_git(["commit", "-m", message], cwd=work)


def _shared_initial_commit(work: Path) -> None:
    _commit_file(work, "README.md", "initial\n", "initial commit")
    _run_git(["branch", "-M", BASE_BRANCH], cwd=work)
    _run_git(["push", "-u", "origin", BASE_BRANCH], cwd=work)


def _diverge_and_rebase(work: Path) -> str:
    """Push the working branch's commits, then the base branch's diverging commits, then
    attempt the rebase exactly as `dev-team:monitor-pr` would. Returns rebase_onto()'s result
    ("rebased" or "conflict") so callers can assert the scenario actually produced a
    conflict."""
    _run_git(["push", "-u", "origin", WORKING_BRANCH], cwd=work)

    _run_git(["checkout", BASE_BRANCH], cwd=work)
    _run_git(["push", "origin", BASE_BRANCH], cwd=work)

    _run_git(["checkout", WORKING_BRANCH], cwd=work)
    return rebase_onto(WORKING_BRANCH, BASE_BRANCH, work)


def build_single_file_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_pair(dest)
    _shared_initial_commit(work)
    _commit_file(work, "CHANGELOG.md", "# Changelog\n\n## Unreleased\n", "add changelog")

    _run_git(["checkout", "-b", WORKING_BRANCH], cwd=work)
    _commit_file(
        work,
        "CHANGELOG.md",
        "# Changelog\n\n## Unreleased\n- Add rebase conflict resolution skill\n",
        "changelog: resolve-rebase-conflict",
    )

    _run_git(["checkout", BASE_BRANCH], cwd=work)
    _commit_file(
        work,
        "CHANGELOG.md",
        "# Changelog\n\n## Unreleased\n- Add PR event detector\n",
        "changelog: PR event detector (merged upstream)",
    )

    result = _diverge_and_rebase(work)
    if result != "conflict":
        raise RuntimeError(f"single-file scenario expected a conflict, got {result!r}")

    task_brief = (
        "Task: build the resolve-rebase-conflict skill.\n\n"
        "This task's CHANGELOG.md entry is exactly:\n"
        "- Add rebase conflict resolution skill\n\n"
        "Convention: append new entries under `## Unreleased` — never drop an entry another "
        "task already merged there."
    )
    return ScenarioFixture(work, WORKING_BRANCH, BASE_BRANCH, task_brief, "resolved")


def build_multi_file_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_pair(dest)
    _shared_initial_commit(work)
    _commit_file(work, "CHANGELOG.md", "# Changelog\n\n## Unreleased\n", "add changelog")
    _commit_file(
        work, "config/settings.json", '{\n  "max_retries": 3\n}\n', "add settings"
    )

    _run_git(["checkout", "-b", WORKING_BRANCH], cwd=work)
    _commit_files(
        work,
        {
            "CHANGELOG.md": (
                "# Changelog\n\n## Unreleased\n- Add rebase conflict resolution skill\n"
            ),
            "config/settings.json": '{\n  "max_retries": 5\n}\n',
        },
        "resolve-rebase-conflict: changelog entry + bump max_retries to 5",
    )

    _run_git(["checkout", BASE_BRANCH], cwd=work)
    _commit_files(
        work,
        {
            "CHANGELOG.md": "# Changelog\n\n## Unreleased\n- Add PR event detector\n",
            "config/settings.json": '{\n  "max_retries": 4\n}\n',
        },
        "merged upstream: PR event detector changelog entry + max_retries bump to 4 (now superseded)",
    )

    result = _diverge_and_rebase(work)
    if result != "conflict":
        raise RuntimeError(f"multi-file scenario expected a conflict, got {result!r}")

    task_brief = (
        "Task: build the resolve-rebase-conflict skill.\n\n"
        "This task's CHANGELOG.md entry is exactly:\n"
        "- Add rebase conflict resolution skill\n\n"
        "Convention: append new entries under `## Unreleased` — never drop an entry another "
        "task already merged there.\n\n"
        "This task also bumps `config/settings.json`'s `max_retries` to 5 to reduce flaky CI "
        "failures. 5 is the final target value regardless of any interim value another task "
        "already merged there."
    )
    return ScenarioFixture(work, WORKING_BRANCH, BASE_BRANCH, task_brief, "resolved")


def build_unresolvable_scenario(dest: Path) -> ScenarioFixture:
    work = _init_repo_pair(dest)
    _shared_initial_commit(work)
    _commit_file(
        work,
        "config/retry_policy.json",
        '{\n  "backoff_multiplier": 1.5\n}\n',
        "add retry policy",
    )

    _run_git(["checkout", "-b", WORKING_BRANCH], cwd=work)
    _commit_file(
        work,
        "config/retry_policy.json",
        '{\n  "backoff_multiplier": 2.5\n}\n',
        "adjust retry backoff multiplier",
    )

    _run_git(["checkout", BASE_BRANCH], cwd=work)
    _commit_file(
        work,
        "config/retry_policy.json",
        '{\n  "backoff_multiplier": 2.0\n}\n',
        "adjust retry backoff multiplier (merged upstream, unrelated task)",
    )

    result = _diverge_and_rebase(work)
    if result != "conflict":
        raise RuntimeError(f"unresolvable scenario expected a conflict, got {result!r}")

    task_brief = (
        "Task: build the resolve-rebase-conflict skill.\n\n"
        "This task adjusts the retry backoff multiplier in `config/retry_policy.json` for "
        "better resilience under load."
    )
    return ScenarioFixture(work, WORKING_BRANCH, BASE_BRANCH, task_brief, "unresolved")


_BUILDERS = {
    "single-file": build_single_file_scenario,
    "multi-file": build_multi_file_scenario,
    "unresolvable": build_unresolvable_scenario,
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
    print(f"working_branch: {fixture.working_branch}")
    print(f"base_branch: {fixture.base_branch}")
    print(f"expected_outcome: {fixture.expected_outcome}")
    print("task_brief:")
    print(fixture.task_brief)


if __name__ == "__main__":
    main()
