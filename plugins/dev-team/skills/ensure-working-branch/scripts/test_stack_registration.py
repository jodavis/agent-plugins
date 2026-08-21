"""Tests for stack_registration.py — the two pieces of genuinely branching decision logic
`ensure-working-branch`'s prose SKILL.md invokes via `Bash`:

- compute_stack_anchor(): picks which of a task's own declared dependencies its working branch
  should be based on — whichever sorts latest in the epic's validated document order — or `None`
  when the task has no dependencies (base on the feature branch instead). Every dependency is
  guaranteed already `done` by the time a task starts (`task_readiness.py`'s `is_task_eligible`),
  so there is no backfill/placeholder concern the way the old eager-registration design had.
- verify_branch_identity(): the closes-#126 guardrail — confirms the branch actually checked
  out after registration is genuinely the task's own working branch, and never the shared
  feature branch.

Covers:
- compute_stack_anchor: no dependencies, one dependency, multiple dependencies (picks the one
  latest in document order regardless of listed order)
- verify_branch_identity: matching branch (no error), current branch is the feature branch
  (closes #126), current branch is neither the working branch nor the feature branch
- main() CLI wrapper ('anchor' and 'verify' subcommands): one narrow integration test per
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
# compute_stack_anchor — no declared dependencies
# ---------------------------------------------------------------------------

class TestComputeStackAnchorNoDependencies:
    def test_no_dependencies_returns_none(self):
        # Arrange
        from stack_registration import compute_stack_anchor
        order = ["ADR-1", "ADR-2", "ADR-3"]

        # Act
        result = compute_stack_anchor("ADR-1", [], order)

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# compute_stack_anchor — a single declared dependency
# ---------------------------------------------------------------------------

class TestComputeStackAnchorSingleDependency:
    def test_single_dependency_returns_it(self):
        # Arrange
        from stack_registration import compute_stack_anchor
        order = ["ADR-1", "ADR-2", "ADR-3"]

        # Act
        result = compute_stack_anchor("ADR-3", ["ADR-1"], order)

        # Assert
        assert result == "ADR-1"


# ---------------------------------------------------------------------------
# compute_stack_anchor — multiple dependencies picks the one latest in document order,
# regardless of the order they're listed in
# ---------------------------------------------------------------------------

class TestComputeStackAnchorMultipleDependencies:
    def test_multiple_dependencies_picks_latest_in_document_order(self):
        # Arrange
        from stack_registration import compute_stack_anchor
        order = ["ADR-1", "ADR-2", "ADR-3", "ADR-4"]

        # Act
        result = compute_stack_anchor("ADR-4", ["ADR-3", "ADR-1"], order)

        # Assert
        assert result == "ADR-3"


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
# main() CLI wrapper — 'anchor' subcommand
# ---------------------------------------------------------------------------

class TestMainAnchorCliWrapper:
    def test_main_anchor_with_dependency_prints_anchor_task(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        spec_path = tmp_path / "spec.md"
        spec_path.write_text(
            spec_text_for([("ADR-1", "— none —"), ("ADR-2", "ADR-1")]), encoding="utf-8"
        )

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "anchor", "ADR-2", str(spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"anchor_task": "ADR-1"}

    def test_main_anchor_first_task_in_stack_prints_null_anchor(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        spec_path = tmp_path / "spec.md"
        spec_path.write_text(spec_text_for([("ADR-1", "— none —")]), encoding="utf-8")

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "anchor", "ADR-1", str(spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"anchor_task": None}

    def test_main_anchor_missing_spec_file_prints_error_and_exits_nonzero(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        missing_spec_path = tmp_path / "does-not-exist.md"

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "anchor", "ADR-1", str(missing_spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode != 0
        assert "Error:" in result.stderr

    def test_main_anchor_target_task_not_in_order_prints_error_and_exits_nonzero(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        spec_path = tmp_path / "spec.md"
        spec_path.write_text(spec_text_for([("ADR-1", "— none —")]), encoding="utf-8")

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "stack_registration.py"), "anchor", "ADR-99", str(spec_path)],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode != 0
        assert "Error:" in result.stderr
        assert "ADR-99" in result.stderr


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
