"""Tests for stack_registration.py — the two pieces of genuinely branching decision logic
`ensure-working-branch`'s prose SKILL.md invokes via `Bash` for ADR-375's lazy, recursive stack
branch registration:

- compute_registration_plan(): walks backward from a task's position in the epic's validated
  stack order until it finds an already-registered ancestor, returning the ordered list of
  tasks that still need a branch registered (oldest first) plus the already-registered task to
  anchor the first of them on.
- is_added_to_stack(): reads a task's own context file to check its `added_to_stack` field,
  false for a task with no context file yet (an unstarted human task).
- verify_branch_identity(): the closes-#126 guardrail — confirms the branch actually checked
  out after registration is genuinely the task's own working branch, and never the shared
  feature branch.

Covers:
- compute_registration_plan: no backfill needed, one-level backfill, multi-level backfill, the
  first task in the stack (no predecessor at all), and a target task missing from the order
- is_added_to_stack: no context file, added_to_stack true, added_to_stack false (default)
- verify_branch_identity: matching branch (no error), current branch is the feature branch
  (closes #126), current branch is neither the working branch nor the feature branch
- main() CLI wrapper ('plan' and 'verify' subcommands): one narrow integration test per
  subcommand's primary happy path, plus their primary error paths, covering the wiring
  `ensure-working-branch` relies on to call this script via `Bash`
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent


def spec_text_for(order_with_dependencies: list[tuple[str, str]]) -> str:
    """Build minimal '## Tasks' spec text task_dependencies.py's TASK_HEADING_RE/DEPENDS_ON_RE
    can parse, from a list of (task_key, depends_on_value) pairs in document order."""
    sections = []
    for task_key, depends_on in order_with_dependencies:
        sections.append(
            f"### [{task_key}: Title](https://example.com/{task_key}) \U0001f916\n\n"
            f"**Depends on:** {depends_on}\n"
        )
    return "## Tasks\n\n" + "\n".join(sections)


# ---------------------------------------------------------------------------
# compute_registration_plan — no backfill needed (predecessor already registered)
# ---------------------------------------------------------------------------

class TestComputeRegistrationPlanNoBackfillNeeded:
    def test_predecessor_already_registered_returns_plan_of_just_this_task(self):
        # Arrange
        from stack_registration import compute_registration_plan
        order = ["ADR-1", "ADR-2", "ADR-3"]
        registered = {"ADR-1", "ADR-2"}

        # Act
        result = compute_registration_plan("ADR-3", order, is_registered=lambda t: t in registered)

        # Assert
        assert result.plan == ["ADR-3"]
        assert result.anchor_task == "ADR-2"


# ---------------------------------------------------------------------------
# compute_registration_plan — one-level backfill (predecessor unregistered, its own
# predecessor already registered)
# ---------------------------------------------------------------------------

class TestComputeRegistrationPlanOneLevelBackfill:
    def test_unregistered_predecessor_backfilled_before_this_task(self):
        # Arrange
        from stack_registration import compute_registration_plan
        order = ["ADR-1", "ADR-2", "ADR-3"]
        registered = {"ADR-1"}

        # Act
        result = compute_registration_plan("ADR-3", order, is_registered=lambda t: t in registered)

        # Assert
        assert result.plan == ["ADR-2", "ADR-3"]
        assert result.anchor_task == "ADR-1"


# ---------------------------------------------------------------------------
# compute_registration_plan — multi-level backfill (walks back to the start of the stack)
# ---------------------------------------------------------------------------

class TestComputeRegistrationPlanMultiLevelBackfill:
    def test_no_registered_ancestor_backfills_all_the_way_to_the_first_task(self):
        # Arrange
        from stack_registration import compute_registration_plan
        order = ["ADR-1", "ADR-2", "ADR-3", "ADR-4"]

        # Act
        result = compute_registration_plan("ADR-4", order, is_registered=lambda t: False)

        # Assert
        assert result.plan == ["ADR-1", "ADR-2", "ADR-3", "ADR-4"]
        assert result.anchor_task is None


# ---------------------------------------------------------------------------
# compute_registration_plan — this task is first in the stack (no predecessor at all)
# ---------------------------------------------------------------------------

class TestComputeRegistrationPlanFirstTaskInStack:
    def test_first_task_in_stack_returns_plan_of_just_itself_with_no_anchor(self):
        # Arrange
        from stack_registration import compute_registration_plan
        order = ["ADR-1", "ADR-2", "ADR-3"]

        # Act
        result = compute_registration_plan("ADR-1", order, is_registered=lambda t: False)

        # Assert
        assert result.plan == ["ADR-1"]
        assert result.anchor_task is None


# ---------------------------------------------------------------------------
# compute_registration_plan — target task missing from the stack order
# ---------------------------------------------------------------------------

class TestComputeRegistrationPlanTargetNotInOrder:
    def test_target_task_not_in_order_raises_value_error(self):
        # Arrange
        from stack_registration import compute_registration_plan
        order = ["ADR-1", "ADR-2"]

        # Act / Assert
        with pytest.raises(ValueError, match="ADR-99"):
            compute_registration_plan("ADR-99", order, is_registered=lambda t: False)


# ---------------------------------------------------------------------------
# is_added_to_stack — no context file yet
# ---------------------------------------------------------------------------

class TestIsAddedToStackNoContextFile:
    def test_no_context_file_returns_false(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from stack_registration import is_added_to_stack

        # Act
        result = is_added_to_stack("ADR-999")

        # Assert
        assert result is False


# ---------------------------------------------------------------------------
# is_added_to_stack — existing context file, true vs. default false
# ---------------------------------------------------------------------------

class TestIsAddedToStackExistingContextFile:
    @pytest.mark.parametrize(
        "added_to_stack, expected",
        [
            pytest.param(True, True, id="added_to_stack_true"),
            pytest.param(False, False, id="added_to_stack_false_default"),
        ],
    )
    def test_existing_context_file_returns_its_added_to_stack_value(
        self, tmp_path, monkeypatch, added_to_stack, expected
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from stack_registration import is_added_to_stack

        path = compute_context_path("ADR-1", get_repo_slug())
        PipelineContext(work_item_id="ADR-1", added_to_stack=added_to_stack).save(path)

        # Act
        result = is_added_to_stack("ADR-1")

        # Assert
        assert result is expected


# ---------------------------------------------------------------------------
# verify_branch_identity — matching branch, no error
# ---------------------------------------------------------------------------

class TestVerifyBranchIdentityMatch:
    def test_current_branch_matches_working_branch_does_not_raise(self):
        # Arrange
        from stack_registration import verify_branch_identity

        # Act / Assert (no exception)
        verify_branch_identity(
            current_branch="dev/claude/ADR-3",
            working_branch="dev/claude/ADR-3",
            feature_branch="feature/ADR-1",
        )


# ---------------------------------------------------------------------------
# verify_branch_identity — HEAD is the feature branch (closes #126)
# ---------------------------------------------------------------------------

class TestVerifyBranchIdentityFeatureBranchMismatch:
    def test_current_branch_is_feature_branch_raises_mismatch_error(self):
        # Arrange
        from stack_registration import BranchIdentityMismatchError, verify_branch_identity

        # Act / Assert
        with pytest.raises(BranchIdentityMismatchError, match="feature branch"):
            verify_branch_identity(
                current_branch="feature/ADR-1",
                working_branch="dev/claude/ADR-3",
                feature_branch="feature/ADR-1",
            )


# ---------------------------------------------------------------------------
# verify_branch_identity — HEAD is neither the working branch nor the feature branch
# ---------------------------------------------------------------------------

class TestVerifyBranchIdentityGenericMismatch:
    def test_current_branch_is_neither_working_nor_feature_branch_raises_mismatch_error(self):
        # Arrange
        from stack_registration import BranchIdentityMismatchError, verify_branch_identity

        # Act / Assert
        with pytest.raises(BranchIdentityMismatchError, match="dev/claude/ADR-99"):
            verify_branch_identity(
                current_branch="dev/claude/ADR-99",
                working_branch="dev/claude/ADR-3",
                feature_branch="feature/ADR-1",
            )


# ---------------------------------------------------------------------------
# main() CLI wrapper — 'plan' subcommand
# ---------------------------------------------------------------------------

class TestMainPlanCliWrapper:
    def test_main_plan_no_backfill_needed_prints_plan_and_anchor_task(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        PipelineContext(work_item_id="ADR-1", added_to_stack=True).save(
            compute_context_path("ADR-1", get_repo_slug())
        )
        spec_path = tmp_path / "spec.md"
        spec_path.write_text(
            spec_text_for([("ADR-1", "— none —"), ("ADR-2", "ADR-1")]), encoding="utf-8"
        )

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "plan", "ADR-2", str(spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"plan": ["ADR-2"], "anchor_task": "ADR-1"}

    def test_main_plan_missing_spec_file_prints_error_and_exits_nonzero(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        missing_spec_path = tmp_path / "does-not-exist.md"

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "plan", "ADR-1", str(missing_spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode != 0
        assert "Error:" in result.stderr


# ---------------------------------------------------------------------------
# main() CLI wrapper — 'verify' subcommand
# ---------------------------------------------------------------------------

class TestMainVerifyCliWrapper:
    def test_main_verify_matching_branch_exits_zero_with_no_output(self):
        # Act
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS_DIR / "stack_registration.py"),
                "verify", "dev/claude/ADR-3", "dev/claude/ADR-3", "feature/ADR-1",
            ],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0

    def test_main_verify_mismatched_branch_prints_error_and_exits_nonzero(self):
        # Act
        result = subprocess.run(
            [
                sys.executable, str(SCRIPTS_DIR / "stack_registration.py"),
                "verify", "feature/ADR-1", "dev/claude/ADR-3", "feature/ADR-1",
            ],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode != 0
        assert "Error:" in result.stderr
        assert "closes #126" in result.stderr
