"""Fixture builder for the workflow-troubleshoot skill's dry-run harness.

Builds one of seven named scenarios: a local clone of a dedicated, disposable GitHub repo
(standing in for `<skill-dir>`'s resolved plugin checkout — see `workflow-troubleshoot`'s "Before
diagnosing" section), a throwaway workflow context file (following `use-context-file`'s
section-sentinel format, carrying a `Project Configuration` section with this scenario's
`troubleshooter.can-fix`/`can-push-fix` flags), and — for the match scenarios — real issues (and,
for the linked-PR/stacked-PR scenarios, real branches/PRs) seeded on that disposable repo via the
`gh` CLI, so a dry run exercises the skill's search/dedup/logging and fix/draft-PR steps against
real GitHub state, the same way `resolve-rebase-conflict`'s harness exercises real git subprocess
calls rather than hand-crafted state.

The disposable repo is `jodavis-claude/dev-team-troubleshooter-fixtures`, not the
`jodavis/dev-team-troubleshooter-fixtures` the spec suggested as an example name: the
`jodavis-claude` account that runs this harness has no permission to create a repo inside the
`jodavis` user namespace (GitHub only allows that for org namespaces, and `jodavis` is a user
account, not an org). It was created once, ahead of authoring this file, with its own
`troubleshooter` label pre-created (mirroring the label already on `jodavis/agent-plugins`) — see
this file's own commit for that one-time setup, not runtime logic here.

Scenarios:
- "no-match": one existing troubleshooter-labeled issue describing an unrelated problem is
  seeded. This occurrence's symptoms don't match it, so the skill should diagnose fresh and file
  a distinct new issue rather than reusing the unrelated one.
- "reusable-workaround-match": one existing issue's Symptoms/Workaround sections closely match
  this occurrence. The skill should apply the workaround, add an occurrence comment, and skip
  fresh diagnosis entirely (no new issue filed).
- "failed-workaround-match": one existing issue's Workaround doesn't actually address this
  occurrence's real (differently-rooted) problem. The skill should add a comment describing the
  failure, then diagnose fresh and file a new issue cross-linked to the original.
- "linked-pr-match": one existing issue links an unmerged PR against the disposable repo. The
  skill should recognize it as unmerged, treat its branch as the fix starting point, and update
  the matched issue with the freshly-found workaround rather than filing a duplicate.
- "no-identifiable-cause": a genuinely transient, non-reproducible blip with nothing concrete to
  describe. The skill should write nothing at all — no new issue, no comment on any issue.
- "can-fix-only-local-merge": `can-fix` set, `can-push-fix` not set, against a concretely
  fixable bug seeded directly in the local checkout. The skill should commit the fix on a
  `troubleshooter/<slug>` branch and merge it locally into the checked-out branch — no push, no
  PR.
- "can-fix-can-push-fix-stacked-pr": both flags set, against a different concretely fixable bug.
  The skill should commit the fix on a `troubleshooter/<slug>` branch, add it to a `gh stack`,
  submit it (pushing and opening a draft PR), and overwrite that PR's title/body to match
  `create-pr`'s structured body convention, including `Closes #<issue-number>`.
"""

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

FIXTURE_REPO = "jodavis-claude/dev-team-troubleshooter-fixtures"
FIXTURE_REPO_URL = f"https://github.com/{FIXTURE_REPO}.git"
DEFAULT_BRANCH = "main"
TROUBLESHOOTER_LABEL = "troubleshooter"

SCENARIOS = (
    "no-match",
    "reusable-workaround-match",
    "failed-workaround-match",
    "linked-pr-match",
    "no-identifiable-cause",
    "can-fix-only-local-merge",
    "can-fix-can-push-fix-stacked-pr",
)


@dataclass
class ScenarioFixture:
    """Everything a dry run of `workflow-troubleshoot` needs: the local checkout standing in for
    `<skill-dir>`'s resolved plugin repo, the throwaway context file, the `--problem` argument to
    pass, this scenario's `can-fix`/`can-push-fix` flags (already embedded in the context file's
    `Project Configuration` section too, for convenience), any issue seeded ahead of the dry run,
    and the outcomes the harness expects: whether a new issue should be filed, whether an
    existing matched issue should be updated, whether a documented workaround should be reused,
    and whether a local-merge or stacked-PR fix should result."""

    checkout: Path
    context_file: Path
    problem: str
    can_fix: bool
    can_push_fix: bool
    seeded_issue_number: Optional[int]
    seeded_issue_url: Optional[str]
    expected_new_issue_filed: bool
    expected_matched_issue_updated: bool
    expected_workaround_reused: bool
    expected_local_merge_fix: bool
    expected_stacked_pr_fix: bool
    description: str


def _run(args: list[str], cwd: Optional[Path] = None, timeout: int = 30) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {result.stderr}")
    return result


def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return _run(["git", *args], cwd=cwd, timeout=timeout)


def _run_gh(args: list[str], cwd: Optional[Path] = None, timeout: int = 30) -> subprocess.CompletedProcess:
    return _run(["gh", *args], cwd=cwd, timeout=timeout)


def _clone_checkout(dest: Path) -> Path:
    """Clone the disposable fixture repo — this stands in for `<skill-dir>`'s resolved plugin
    checkout for the duration of one dry run."""
    checkout = dest / "checkout"
    _run_git(["clone", FIXTURE_REPO_URL, str(checkout)], cwd=dest)
    _run_git(["config", "user.email", "fixture@example.com"], cwd=checkout)
    _run_git(["config", "user.name", "Fixture"], cwd=checkout)
    return checkout


def _create_issue(title: str, body: str) -> tuple[int, str]:
    result = _run_gh(
        [
            "issue", "create",
            "--repo", FIXTURE_REPO,
            "--title", title,
            "--body", body,
            "--label", TROUBLESHOOTER_LABEL,
        ]
    )
    url = result.stdout.strip().splitlines()[-1]
    return int(url.rsplit("/", 1)[-1]), url


def _comment_issue(number: int, body: str) -> None:
    _run_gh(["issue", "comment", str(number), "--repo", FIXTURE_REPO, "--body", body])


def _create_branch_with_commit(
    checkout: Path, branch: str, relative_path: str, content: str, message: str
) -> None:
    _run_git(["checkout", "-b", branch], cwd=checkout)
    file_path = checkout / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    _run_git(["add", relative_path], cwd=checkout)
    _run_git(["commit", "-m", message], cwd=checkout)
    _run_git(["checkout", DEFAULT_BRANCH], cwd=checkout)


def _push_branch(checkout: Path, branch: str) -> None:
    _run_git(["push", "-u", "origin", branch], cwd=checkout)


def _create_pr(checkout: Path, branch: str, title: str, body: str) -> tuple[int, str]:
    result = _run_gh(
        [
            "pr", "create",
            "--repo", FIXTURE_REPO,
            "--head", branch,
            "--base", DEFAULT_BRANCH,
            "--title", title,
            "--body", body,
        ],
        cwd=checkout,
    )
    url = result.stdout.strip().splitlines()[-1]
    return int(url.rsplit("/", 1)[-1]), url


def _seed_buggy_script(
    checkout: Path, relative_path: str, buggy_content: str, test_relative_path: str, test_content: str
) -> None:
    """Commit a small, concretely-fixable bug directly onto the checked-out branch in the LOCAL
    clone only (never pushed) — the entry state the `can-fix` scenarios expect: a real, isolated
    defect `workflow-troubleshoot` can find and fix without touching the shared remote."""
    _write_file(checkout, relative_path, buggy_content)
    _write_file(checkout, test_relative_path, test_content)
    _run_git(["add", relative_path, test_relative_path], cwd=checkout)
    _run_git(["commit", "-m", "seed a concretely-fixable bug for the fixture harness"], cwd=checkout)


def _write_file(work: Path, relative_path: str, content: str) -> None:
    file_path = work / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)


def _write_context_file(
    dest: Path,
    problem: str,
    *,
    can_fix: bool = False,
    can_push_fix: bool = False,
    pending_agent: str = "developer",
    consecutive_failures: int = 3,
    failing_section_name: str = "Implementation Summary",
    failing_section_body: str = "",
) -> Path:
    """A throwaway workflow context file, following `use-context-file`'s section-sentinel
    format, carrying the failing pipeline state "Diagnosis steps" reads plus a minimal
    `Project Configuration` section carrying this scenario's `troubleshooter.can-fix`/
    `can-push-fix` flags (the same shape `init-context-file.py` writes in the real pipeline)."""
    context_file = dest / "fixture-context.md"
    project_config = json.dumps(
        {"troubleshooter": {"can-fix": can_fix, "can-push-fix": can_push_fix}}, indent=2
    )
    body = (
        "---\n"
        "work_item_id: FIZZLE-1\n"
        "spec_path: \n"
        "state: implementing\n"
        "troubleshooter_input: \n"
        f"pending_agent: {pending_agent}\n"
        f"consecutive_failures: {consecutive_failures}\n"
        "signoff_cycle_count: 0\n"
        "review_cycle_count: 0\n"
        "---\n\n"
        "# FIZZLE-1 Dev Team Context\n\n"
        "<!-- section:Project Configuration -->\n\n"
        f"{project_config}\n\n"
        f"<!-- section:{failing_section_name} -->\n\n"
        f"{failing_section_body}\n"
    )
    context_file.write_text(body)
    return context_file


def build_no_match_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    number, url = _create_issue(
        title="Reviewer agent times out fetching PR diff",
        body=(
            "## Symptoms\n"
            "Reviewer step failed 3 times in a row while fetching the PR diff; each failure "
            "logged a GitHub API 502.\n\n"
            "## Workaround\n"
            "Retry the review step after a short delay; the 502 is transient."
        ),
    )
    context_file = _write_context_file(
        dest,
        problem="consecutive_failures",
        pending_agent="implement",
        consecutive_failures=3,
        failing_section_body="(empty — Developer agent produced no Implementation Summary section three runs in a row)",
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="consecutive_failures",
        can_fix=False,
        can_push_fix=False,
        seeded_issue_number=number,
        seeded_issue_url=url,
        expected_new_issue_filed=True,
        expected_matched_issue_updated=False,
        expected_workaround_reused=False,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=False,
        description=(
            "An unrelated troubleshooter-labeled issue exists; this occurrence's symptoms don't "
            "match it, so the skill should diagnose fresh and file a distinct new issue."
        ),
    )


def build_reusable_workaround_match_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    number, url = _create_issue(
        title="Developer agent writes no Implementation Summary section three runs in a row",
        body=(
            "## Symptoms\n"
            "`consecutive_failures` reaches 3 with `pending_agent` stuck at `implement` and no "
            "`Implementation Summary` section ever written to the context file.\n\n"
            "## Workaround\n"
            "Set the context file's `state` field back to `implementing` and reset "
            "`consecutive_failures` to `0`, then retry."
        ),
    )
    context_file = _write_context_file(
        dest,
        problem="consecutive_failures",
        pending_agent="implement",
        consecutive_failures=3,
        failing_section_body="(empty — Developer agent produced no Implementation Summary section three runs in a row)",
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="consecutive_failures",
        can_fix=False,
        can_push_fix=False,
        seeded_issue_number=number,
        seeded_issue_url=url,
        expected_new_issue_filed=False,
        expected_matched_issue_updated=True,
        expected_workaround_reused=True,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=False,
        description=(
            "The matched issue's documented workaround applies cleanly to this occurrence's "
            "identical symptoms — the skill should reuse it and skip fresh diagnosis."
        ),
    )


def build_failed_workaround_match_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    number, url = _create_issue(
        title="Developer agent writes no Implementation Summary section three runs in a row",
        body=(
            "## Symptoms\n"
            "`consecutive_failures` reaches 3 with `pending_agent` stuck at `implement` and no "
            "`Implementation Summary` section ever written to the context file.\n\n"
            "## Workaround\n"
            "Set the context file's `state` field back to `implementing` and reset "
            "`consecutive_failures` to `0`, then retry."
        ),
    )
    # This occurrence's real root cause is a stuck review cycle, not a stuck implement step —
    # the matched issue's documented workaround (reset state to "implementing") does not
    # address it, even though the shared `consecutive_failures` trigger name matched.
    context_file = _write_context_file(
        dest,
        problem="consecutive_failures",
        pending_agent="review",
        consecutive_failures=3,
        failing_section_name="Review Notes",
        failing_section_body=(
            "Reviewer has posted the identical unresolved comment on every one of the last 3 "
            "review/fix cycles: 'missing test coverage for the error branch.' The fix agent's "
            "own summary claims the coverage was added each time."
        ),
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="consecutive_failures",
        can_fix=False,
        can_push_fix=False,
        seeded_issue_number=number,
        seeded_issue_url=url,
        expected_new_issue_filed=True,
        expected_matched_issue_updated=False,
        expected_workaround_reused=False,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=False,
        description=(
            "The matched issue's documented workaround (reset `state` to `implementing`) does "
            "not fit this occurrence's real symptom (a stuck review/fix loop) despite the "
            "shared trigger name — the skill should recognize the mismatch, comment on the "
            "original describing the failure, then diagnose fresh and file a new, cross-linked "
            "issue."
        ),
    )


def build_linked_pr_match_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    run_id = uuid.uuid4().hex[:8]
    branch = f"linked-pr-fixture/{run_id}"
    _create_branch_with_commit(
        checkout,
        branch,
        "tools/deadlock_guard.py",
        "def should_break_cycle(count):\n    return count >= 2\n",
        "propose a fix for the signoff deadlock",
    )
    _push_branch(checkout, branch)
    pr_number, pr_url = _create_pr(
        checkout,
        branch,
        title="Break signoff deadlock after 2 cycles instead of never",
        body="Proposed fix — not yet merged.",
    )
    issue_number, issue_url = _create_issue(
        title="Sign-off cycles indefinitely without resolution",
        body=(
            "## Symptoms\n"
            "`signoff_cycle_count` keeps incrementing past 2 with the reviewer and researcher "
            "repeating the same disagreement.\n\n"
            f"PR: {pr_url}"
        ),
    )
    context_file = _write_context_file(
        dest,
        problem="signoff_deadlock",
        pending_agent="reviewer",
        consecutive_failures=0,
        failing_section_name="Signoff Review",
        failing_section_body=(
            "signoff_cycle_count: 2. Reviewer and researcher have restated the same disagreement "
            "on both cycles with no new information."
        ),
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="signoff_deadlock",
        can_fix=False,
        can_push_fix=False,
        seeded_issue_number=issue_number,
        seeded_issue_url=issue_url,
        expected_new_issue_filed=False,
        expected_matched_issue_updated=True,
        expected_workaround_reused=False,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=False,
        description=(
            f"The matched issue links an unmerged PR ({pr_url}) — the skill should recognize it "
            "as unmerged, treat its branch as the fix starting point rather than writing one "
            "from scratch, and update the matched issue (not file a new one) with the freshly "
            "diagnosed workaround."
        ),
    )


def build_no_identifiable_cause_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    context_file = _write_context_file(
        dest,
        problem="one MCP tool call timed out once; an identical retry succeeded immediately with no other symptom",
        pending_agent="",
        consecutive_failures=0,
        failing_section_name="Implementation Summary",
        failing_section_body="(a normal, complete summary — nothing wrong with this run's output)",
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem=(
            "one MCP tool call timed out once; an identical retry succeeded immediately with no "
            "other symptom"
        ),
        can_fix=False,
        can_push_fix=False,
        seeded_issue_number=None,
        seeded_issue_url=None,
        expected_new_issue_filed=False,
        expected_matched_issue_updated=False,
        expected_workaround_reused=False,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=False,
        description=(
            "A genuinely transient, non-reproducible blip with nothing concrete to describe — "
            "the skill should write nothing at all, no new issue and no comment."
        ),
    )


def build_can_fix_only_local_merge_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    _seed_buggy_script(
        checkout,
        "tools/greet.py",
        'def greet(name):\n    return "Hell " + name  # BUG: missing "o"\n',
        "tools/test_greet.py",
        (
            "from greet import greet\n\n\n"
            "def test_greet_returns_hello_name():\n"
            '    assert greet("World") == "Hello World"\n'
        ),
    )
    context_file = _write_context_file(
        dest,
        problem="validate_failed",
        pending_agent="validate",
        consecutive_failures=1,
        failing_section_name="Validation Log",
        failing_section_body=(
            "tools/test_greet.py::test_greet_returns_hello_name FAILED — "
            "AssertionError: 'Hell World' != 'Hello World'"
        ),
        can_fix=True,
        can_push_fix=False,
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="validate_failed",
        can_fix=True,
        can_push_fix=False,
        seeded_issue_number=None,
        seeded_issue_url=None,
        expected_new_issue_filed=True,
        expected_matched_issue_updated=False,
        expected_workaround_reused=False,
        expected_local_merge_fix=True,
        expected_stacked_pr_fix=False,
        description=(
            "`can-fix` is set, `can-push-fix` is not — the skill should fix the seeded bug in "
            "`tools/greet.py`, commit it on a `troubleshooter/<slug>` branch, and merge that "
            "branch locally into the checked-out branch with no push and no PR."
        ),
    )


def build_can_fix_can_push_fix_stacked_pr_scenario(dest: Path) -> ScenarioFixture:
    checkout = _clone_checkout(dest)
    _seed_buggy_script(
        checkout,
        "tools/farewell.py",
        'def farewell(name):\n    return "Bye " + name  # BUG: should be "Goodbye "\n',
        "tools/test_farewell.py",
        (
            "from farewell import farewell\n\n\n"
            "def test_farewell_returns_goodbye_name():\n"
            '    assert farewell("World") == "Goodbye World"\n'
        ),
    )
    context_file = _write_context_file(
        dest,
        problem="validate_failed",
        pending_agent="validate",
        consecutive_failures=1,
        failing_section_name="Validation Log",
        failing_section_body=(
            "tools/test_farewell.py::test_farewell_returns_goodbye_name FAILED — "
            "AssertionError: 'Bye World' != 'Goodbye World'"
        ),
        can_fix=True,
        can_push_fix=True,
    )
    return ScenarioFixture(
        checkout=checkout,
        context_file=context_file,
        problem="validate_failed",
        can_fix=True,
        can_push_fix=True,
        seeded_issue_number=None,
        seeded_issue_url=None,
        expected_new_issue_filed=True,
        expected_matched_issue_updated=False,
        expected_workaround_reused=False,
        expected_local_merge_fix=False,
        expected_stacked_pr_fix=True,
        description=(
            "Both `can-fix` and `can-push-fix` are set — the skill should fix the seeded bug in "
            "`tools/farewell.py`, add it to a `gh stack` on a `troubleshooter/<slug>` branch, "
            "submit the stack (pushing and opening a draft PR), and overwrite that PR's "
            "title/body to match `create-pr`'s structured body convention, including "
            "`Closes #<issue-number>`."
        ),
    )


_BUILDERS = {
    "no-match": build_no_match_scenario,
    "reusable-workaround-match": build_reusable_workaround_match_scenario,
    "failed-workaround-match": build_failed_workaround_match_scenario,
    "linked-pr-match": build_linked_pr_match_scenario,
    "no-identifiable-cause": build_no_identifiable_cause_scenario,
    "can-fix-only-local-merge": build_can_fix_only_local_merge_scenario,
    "can-fix-can-push-fix-stacked-pr": build_can_fix_can_push_fix_stacked_pr_scenario,
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

    print(f"checkout: {fixture.checkout}")
    print(f"context_file: {fixture.context_file}")
    print(f"problem: {fixture.problem}")
    print(f"can_fix: {fixture.can_fix}")
    print(f"can_push_fix: {fixture.can_push_fix}")
    print(f"seeded_issue_number: {fixture.seeded_issue_number}")
    print(f"seeded_issue_url: {fixture.seeded_issue_url}")
    print(f"expected_new_issue_filed: {fixture.expected_new_issue_filed}")
    print(f"expected_matched_issue_updated: {fixture.expected_matched_issue_updated}")
    print(f"expected_workaround_reused: {fixture.expected_workaround_reused}")
    print(f"expected_local_merge_fix: {fixture.expected_local_merge_fix}")
    print(f"expected_stacked_pr_fix: {fixture.expected_stacked_pr_fix}")
    print(f"description: {fixture.description}")


if __name__ == "__main__":
    main()
