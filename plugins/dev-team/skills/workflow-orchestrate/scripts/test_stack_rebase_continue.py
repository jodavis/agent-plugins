"""Tests for stack_rebase_continue.py — rebase_continue() (a one-shot `gh stack rebase --continue`
call that resumes gh-stack's cascading rebase after the currently-conflicted branch's own
git-level rebase has already been completed) and its CLI wrapper main().

Covers:
- rebase_continue: a clean cascade (no rebase left in progress) returns "ok" regardless of the
  op's own reported status; a further conflict higher in the stack (rebase left in progress)
  returns "conflict" even if the op's own exit code is non-zero; an op failure with no rebase in
  progress is a genuine error, raised rather than silently swallowed
- main() CLI wrapper: "ok"/"conflict" results print as JSON, and the error path
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from stack_rebase_continue import main, rebase_continue


# ---------------------------------------------------------------------------
# rebase_continue — a further conflict higher in the stack leaves a rebase in
# progress, regardless of the op's own reported status
# ---------------------------------------------------------------------------

class TestRebaseContinueConflict:
    def test_rebase_continue_rebase_left_in_progress_returns_conflict(self):
        # Arrange
        with patch("stack_rebase_continue.gh_stack.rebase_continue", return_value=("error", "conflict")), \
             patch("stack_rebase_continue._rebase_in_progress", return_value=True):
            # Act
            result = rebase_continue()

        # Assert
        assert result == "conflict"


# ---------------------------------------------------------------------------
# rebase_continue — the cascade reaches a clean state: no rebase left in
# progress and the op itself reported success
# ---------------------------------------------------------------------------

class TestRebaseContinueClean:
    def test_rebase_continue_no_rebase_in_progress_and_op_ok_returns_ok(self):
        # Arrange
        with patch(
            "stack_rebase_continue.gh_stack.rebase_continue",
            return_value=("ok", "Rebased feature/stack-a onto main"),
        ), patch("stack_rebase_continue._rebase_in_progress", return_value=False):
            # Act
            result = rebase_continue()

        # Assert
        assert result == "ok"


# ---------------------------------------------------------------------------
# rebase_continue — the op itself failed and no rebase is in progress: a
# genuine error, not a conflict to loop back on
# ---------------------------------------------------------------------------

class TestRebaseContinueGenuineError:
    def test_rebase_continue_op_errors_with_no_rebase_in_progress_raises(self):
        # Arrange
        with patch(
            "stack_rebase_continue.gh_stack.rebase_continue",
            return_value=("error", "no rebase in progress"),
        ), patch("stack_rebase_continue._rebase_in_progress", return_value=False):
            # Act / Assert
            with pytest.raises(RuntimeError, match="no rebase in progress"):
                rebase_continue()


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    @pytest.mark.parametrize("result", ["ok", "conflict"])
    def test_main_prints_result_json(self, monkeypatch, capsys, result):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_rebase_continue.py"])

        with patch("stack_rebase_continue.rebase_continue", return_value=result):
            # Act
            main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == result

    def test_main_rebase_continue_raises_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_rebase_continue.py"])

        with patch("stack_rebase_continue.rebase_continue", side_effect=RuntimeError("boom")):
            # Act
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Error: could not resume the stack's rebase cascade: boom\n"
