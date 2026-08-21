"""Tests for checkout_stack_pr_for_review.py — the deterministic script behind the
`checkout-stack-pr-for-review` skill.

Covers:
- resolve_head_branch(): a resolvable PR reference (number/URL/branch with an open PR) vs. a
  bare branch name with no open PR (falls back to using the argument directly).
- slugify_review_branch(): the PR-number form vs. the branch-name form (including sanitizing
  characters git branch names can't safely round-trip through a slug).
- checkout_for_review(): dirty-worktree hard stop, `git status` itself failing, `fetch` failing,
  the new-branch path (`checkout --no-track -b`), the existing-branch reuse path (`checkout` +
  `reset --hard`), and a git command failing partway through either path.
- main() CLI wrapper: happy path (prints JSON, exit 0) and a failure surfaced as `Error: ...` on
  stderr with a non-zero exit.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent


def _result(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# resolve_head_branch
# ---------------------------------------------------------------------------

class TestResolveHeadBranch:
    def test_resolvable_pr_reference_returns_head_branch_and_number(self):
        # Arrange
        from checkout_stack_pr_for_review import resolve_head_branch
        mock_run = MagicMock(
            return_value=_result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
        )

        # Act
        with patch("checkout_stack_pr_for_review._run", mock_run):
            head_branch, pr_number = resolve_head_branch("42")

        # Assert
        assert head_branch == "feature/api-routes"
        assert pr_number == 42
        mock_run.assert_called_once_with(
            ["gh", "pr", "view", "42", "--json", "number,headRefName"]
        )

    def test_branch_with_no_open_pr_falls_back_to_argument(self):
        # Arrange
        from checkout_stack_pr_for_review import resolve_head_branch
        mock_run = MagicMock(return_value=_result(returncode=1, stderr="no pull requests found"))

        # Act
        with patch("checkout_stack_pr_for_review._run", mock_run):
            head_branch, pr_number = resolve_head_branch("feature/no-pr-yet")

        # Assert
        assert head_branch == "feature/no-pr-yet"
        assert pr_number is None


# ---------------------------------------------------------------------------
# slugify_review_branch
# ---------------------------------------------------------------------------

class TestSlugifyReviewBranch:
    def test_pr_number_form(self):
        from checkout_stack_pr_for_review import slugify_review_branch
        assert slugify_review_branch("feature/api-routes", 42) == "review/pr-42"

    def test_branch_name_form_sanitizes_unsafe_characters(self):
        from checkout_stack_pr_for_review import slugify_review_branch
        assert slugify_review_branch("feature/api routes!", None) == "review/feature-api-routes"


# ---------------------------------------------------------------------------
# checkout_for_review — dirty worktree is a hard stop
# ---------------------------------------------------------------------------

class TestCheckoutForReviewDirtyWorktree:
    def test_dirty_worktree_raises_without_running_anything_else(self):
        # Arrange
        from checkout_stack_pr_for_review import CheckoutForReviewError, checkout_for_review
        mock_run = MagicMock(return_value=_result(stdout=" M some/file.py\n"))

        # Act / Assert
        with patch("checkout_stack_pr_for_review._run", mock_run):
            with pytest.raises(CheckoutForReviewError, match="not clean"):
                checkout_for_review("42")
        mock_run.assert_called_once_with(["git", "status", "--short"])

    def test_git_status_command_itself_failing_raises(self):
        # Arrange
        from checkout_stack_pr_for_review import CheckoutForReviewError, checkout_for_review
        mock_run = MagicMock(return_value=_result(returncode=1, stderr="not a git repository"))

        # Act / Assert
        with patch("checkout_stack_pr_for_review._run", mock_run):
            with pytest.raises(CheckoutForReviewError, match="git status"):
                checkout_for_review("42")


# ---------------------------------------------------------------------------
# checkout_for_review — fetch failing
# ---------------------------------------------------------------------------

class TestCheckoutForReviewFetchFails:
    def test_fetch_failure_raises(self):
        # Arrange
        from checkout_stack_pr_for_review import CheckoutForReviewError, checkout_for_review

        def side_effect(args):
            if args[:2] == ["git", "status"]:
                return _result(stdout="")
            if args[:2] == ["gh", "pr"]:
                return _result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
            if args[:2] == ["git", "fetch"]:
                return _result(returncode=1, stderr="couldn't find remote ref")
            raise AssertionError(f"unexpected command: {args}")

        # Act / Assert
        with patch("checkout_stack_pr_for_review._run", side_effect=side_effect):
            with pytest.raises(CheckoutForReviewError, match="fetch"):
                checkout_for_review("42")


# ---------------------------------------------------------------------------
# checkout_for_review — new branch path (does not already exist locally)
# ---------------------------------------------------------------------------

class TestCheckoutForReviewNewBranch:
    def test_creates_branch_off_remote_tip(self):
        # Arrange
        from checkout_stack_pr_for_review import checkout_for_review
        calls = []

        def side_effect(args):
            calls.append(args)
            if args[:2] == ["git", "status"]:
                return _result(stdout="")
            if args[:2] == ["gh", "pr"]:
                return _result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
            if args[:2] == ["git", "fetch"]:
                return _result()
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _result(returncode=1)  # branch does not exist locally
            if args[:2] == ["git", "checkout"]:
                return _result()
            raise AssertionError(f"unexpected command: {args}")

        # Act
        with patch("checkout_stack_pr_for_review._run", side_effect=side_effect):
            result = checkout_for_review("42")

        # Assert
        assert result == {"branch": "review/pr-42", "pr_number": 42, "head_branch": "feature/api-routes"}
        assert ["git", "checkout", "--no-track", "-b", "review/pr-42", "origin/feature/api-routes"] in calls

    def test_checkout_dash_b_failure_raises(self):
        # Arrange
        from checkout_stack_pr_for_review import CheckoutForReviewError, checkout_for_review

        def side_effect(args):
            if args[:2] == ["git", "status"]:
                return _result(stdout="")
            if args[:2] == ["gh", "pr"]:
                return _result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
            if args[:2] == ["git", "fetch"]:
                return _result()
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _result(returncode=1)
            if args[:2] == ["git", "checkout"]:
                return _result(returncode=1, stderr="already exists")
            raise AssertionError(f"unexpected command: {args}")

        # Act / Assert
        with patch("checkout_stack_pr_for_review._run", side_effect=side_effect):
            with pytest.raises(CheckoutForReviewError, match="already exists"):
                checkout_for_review("42")


# ---------------------------------------------------------------------------
# checkout_for_review — existing branch path (a prior run for the same PR)
# ---------------------------------------------------------------------------

class TestCheckoutForReviewExistingBranch:
    def test_reuses_and_resets_existing_branch(self):
        # Arrange
        from checkout_stack_pr_for_review import checkout_for_review
        calls = []

        def side_effect(args):
            calls.append(args)
            if args[:2] == ["git", "status"]:
                return _result(stdout="")
            if args[:2] == ["gh", "pr"]:
                return _result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
            if args[:2] == ["git", "fetch"]:
                return _result()
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _result(returncode=0)  # branch already exists locally
            if args[:2] == ["git", "checkout"]:
                return _result()
            if args[:2] == ["git", "reset"]:
                return _result()
            raise AssertionError(f"unexpected command: {args}")

        # Act
        with patch("checkout_stack_pr_for_review._run", side_effect=side_effect):
            result = checkout_for_review("42")

        # Assert
        assert result == {"branch": "review/pr-42", "pr_number": 42, "head_branch": "feature/api-routes"}
        assert ["git", "checkout", "review/pr-42"] in calls
        assert ["git", "reset", "--hard", "origin/feature/api-routes"] in calls
        assert ["git", "checkout", "--no-track", "-b", "review/pr-42", "origin/feature/api-routes"] not in calls

    def test_reset_hard_failure_raises(self):
        # Arrange
        from checkout_stack_pr_for_review import CheckoutForReviewError, checkout_for_review

        def side_effect(args):
            if args[:2] == ["git", "status"]:
                return _result(stdout="")
            if args[:2] == ["gh", "pr"]:
                return _result(stdout='{"number": 42, "headRefName": "feature/api-routes"}')
            if args[:2] == ["git", "fetch"]:
                return _result()
            if args[:3] == ["git", "rev-parse", "--verify"]:
                return _result(returncode=0)
            if args[:2] == ["git", "checkout"]:
                return _result()
            if args[:2] == ["git", "reset"]:
                return _result(returncode=1, stderr="fatal: ambiguous argument")
            raise AssertionError(f"unexpected command: {args}")

        # Act / Assert
        with patch("checkout_stack_pr_for_review._run", side_effect=side_effect):
            with pytest.raises(CheckoutForReviewError, match="ambiguous argument"):
                checkout_for_review("42")


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_happy_path_prints_json(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["checkout_stack_pr_for_review.py", "42"])
        import checkout_stack_pr_for_review

        # Act
        with patch(
            "checkout_stack_pr_for_review.checkout_for_review",
            return_value={"branch": "review/pr-42", "pr_number": 42, "head_branch": "feature/api-routes"},
        ):
            checkout_stack_pr_for_review.main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {
            "branch": "review/pr-42", "pr_number": 42, "head_branch": "feature/api-routes"
        }

    def test_main_failure_prints_error_and_exits_nonzero(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["checkout_stack_pr_for_review.py", "42"])
        import checkout_stack_pr_for_review
        from checkout_stack_pr_for_review import CheckoutForReviewError

        # Act / Assert
        with patch(
            "checkout_stack_pr_for_review.checkout_for_review",
            side_effect=CheckoutForReviewError("worktree is not clean"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                checkout_stack_pr_for_review.main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: worktree is not clean" in captured.err

    def test_main_missing_argument_exits_nonzero(self):
        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "checkout_stack_pr_for_review.py")],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode != 0
        assert "Usage:" in result.stderr
