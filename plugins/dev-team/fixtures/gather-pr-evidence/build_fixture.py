"""Fixture builder for the gather-pr-evidence skill's dry-run harness.

Builds one of two named scenarios: a throwaway local git repo standing in for the "worktree/clone
absolute path" argument `gather-pr-evidence` reads its target-repo project configuration from,
plus the identity of a real, already-merged PR in `jodavis/agent-plugins` for the skill to fetch
its diff/description/comments from during a live dry run (see RUN.md — that fetch only happens in
Step 2 of the dry run procedure, never in this module or in test_build_fixture.py, so building a
scenario here makes no network call).

Both scenarios configure the same two work-tracking providers (`jira`: `ADR-\\d+`, `github`:
`Issue-\\d+`) in the fixture worktree's `.dev-team/config.yaml` — this repo's own real
`work-tracking` config, reused rather than invented — so the only variable between scenarios is
whether the chosen real PR's description/branch name actually contains a match for either
pattern.

Scenarios:
- "with-related-items": jodavis/agent-plugins#103 (branch `dev/claude/Issue-93`, body mentions
  both "Issue-93" and "ADR-314") — the skill should resolve one related work item per provider.
- "no-related-items": jodavis/agent-plugins#230 (branch `dev/claude/plugin-version-check`, body
  contains neither pattern) — the skill should return `related_work_items: []`.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCENARIOS = ("with-related-items", "no-related-items")

_CONFIG_YAML = (
    "work-tracking:\n"
    "  jira:\n"
    '    issue-key-pattern: "ADR-\\\\d+"\n'
    "  github:\n"
    '    issue-key-pattern: "Issue-\\\\d+"\n'
)


@dataclass
class ScenarioFixture:
    """Everything a dry run of `gather-pr-evidence` needs: the fixture worktree the
    related-work-item scan should read its project configuration from, the real PR identity to
    fetch evidence for, and the outcomes the harness expects: whether `related_work_items` should
    come back empty, and which provider kinds (sorted) should appear in it otherwise."""

    worktree: Path
    pr_owner: str
    pr_repo: str
    pr_number: int
    expected_related_work_items_empty: bool
    expected_provider_kinds: list  # sorted list of provider names, e.g. ["github", "jira"]

    @property
    def pr_ref(self) -> str:
        return f"{self.pr_owner}/{self.pr_repo}#{self.pr_number}"


def _run_git(args: list, cwd: Path, timeout: int = 15) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def _init_worktree_with_config(dest: Path) -> Path:
    """A throwaway git repo (so `get-project-configuration`'s `find_repo_root` can locate it) with
    a `.dev-team/config.yaml` configuring both the `jira` and `github` work-tracking providers —
    the entry state both scenarios in this harness start from."""
    work = dest / "work"
    work.mkdir(parents=True, exist_ok=True)
    _run_git(["init"], cwd=work)
    _run_git(["config", "user.email", "fixture@example.com"], cwd=work)
    _run_git(["config", "user.name", "Fixture"], cwd=work)
    config_dir = work / ".dev-team"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(_CONFIG_YAML)
    _run_git(["add", "-A"], cwd=work)
    _run_git(["commit", "-m", "initial commit"], cwd=work)
    return work


def build_with_related_items_scenario(dest: Path) -> ScenarioFixture:
    work = _init_worktree_with_config(dest)
    return ScenarioFixture(
        worktree=work,
        pr_owner="jodavis",
        pr_repo="agent-plugins",
        pr_number=103,
        expected_related_work_items_empty=False,
        expected_provider_kinds=["github", "jira"],
    )


def build_no_related_items_scenario(dest: Path) -> ScenarioFixture:
    work = _init_worktree_with_config(dest)
    return ScenarioFixture(
        worktree=work,
        pr_owner="jodavis",
        pr_repo="agent-plugins",
        pr_number=230,
        expected_related_work_items_empty=True,
        expected_provider_kinds=[],
    )


_BUILDERS = {
    "with-related-items": build_with_related_items_scenario,
    "no-related-items": build_no_related_items_scenario,
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
    print(f"pr_ref: {fixture.pr_ref}")
    print(f"expected_related_work_items_empty: {fixture.expected_related_work_items_empty}")
    print(f"expected_provider_kinds: {fixture.expected_provider_kinds}")


if __name__ == "__main__":
    main()
