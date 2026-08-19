"""Tests for stack_checkout.py — checkout() (a one-shot `gh stack checkout <pr-number>` call that
materializes a stack's membership in the current worktree) and its CLI wrapper main().

Covers:
- checkout: a successful op is silent (no return value, no exception); a failing op raises a
  RuntimeError naming the PR number and the underlying detail
- main() CLI wrapper: success prints "ok" as JSON; a checkout() failure prints an Error message
  and exits 1; a missing/non-integer argument is rejected by argparse before checkout() runs
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from stack_checkout import checkout, main


# ---------------------------------------------------------------------------
# checkout — a successful gh_stack.checkout() call is silent
# ---------------------------------------------------------------------------

class TestCheckoutSuccess:
    def test_checkout_op_succeeds_returns_none_without_raising(self):
        # Arrange
        with patch("stack_checkout.gh_stack.checkout", return_value=("ok", "Switched to branch")) as mock_checkout:
            # Act
            result = checkout(42)

        # Assert
        assert result is None
        mock_checkout.assert_called_once()


# ---------------------------------------------------------------------------
# checkout — a failing gh_stack.checkout() call raises, naming the PR number
# and the underlying detail
# ---------------------------------------------------------------------------

class TestCheckoutFailure:
    def test_checkout_op_fails_raises_runtime_error_naming_pr_and_detail(self):
        # Arrange
        with patch("stack_checkout.gh_stack.checkout", return_value=("error", "no PR found for that number")):
            # Act / Assert
            with pytest.raises(RuntimeError, match="42.*no PR found for that number"):
                checkout(42)


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_success_prints_ok(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_checkout.py", "42"])

        with patch("stack_checkout.checkout", return_value=None) as mock_checkout:
            # Act
            main()

        # Assert
        mock_checkout.assert_called_once_with(42)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == "ok"

    def test_main_checkout_raises_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_checkout.py", "42"])

        with patch("stack_checkout.checkout", side_effect=RuntimeError("boom")):
            # Act
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Error: could not check out the stack: boom\n"

    def test_main_missing_argument_exits_before_calling_checkout(self, monkeypatch):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_checkout.py"])

        with patch("stack_checkout.checkout") as mock_checkout:
            # Act / Assert
            with pytest.raises(SystemExit):
                main()
            mock_checkout.assert_not_called()
