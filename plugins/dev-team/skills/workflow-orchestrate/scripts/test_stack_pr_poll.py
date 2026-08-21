"""Tests for stack_pr_poll.py — poll() (a bounded polling loop over `gh stack sync` and
detect_next_stack_event.detect_next_stack_event()) and its CLI wrapper main().

Covers:
- poll: a genuine conflict (mid-rebase git state left after sync) returns "conflict" immediately
  without calling the detector; a review_comment/ci_failure event returns immediately; a
  task_merged event is untracked silently and the loop continues unless every branch in the
  stack is now merged ("stack_complete"); "no_change" once max_seconds elapses (including
  max_seconds=0, without sleeping); sync runs every iteration; a second, independent poll() call
  is unaffected by what the previous call returned
- _rebase_in_progress: git-dir resolution (absolute/relative), rebase-merge, rebase-apply, no
  rebase in progress, and the git-dir lookup itself failing
- _stack_complete: gh_stack.view() error, no branches, all merged, some not merged
- main() CLI wrapper: dict-result success, "no_change" success, and the error path
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from stack_pr_poll import main, poll, _stack_complete, _rebase_in_progress


# ---------------------------------------------------------------------------
# poll — a genuine conflict left mid-rebase after sync returns "conflict"
# immediately, without ever consulting the detector
# ---------------------------------------------------------------------------

class TestPollConflictDetected:
    def test_poll_rebase_in_progress_after_sync_returns_conflict_without_calling_detector(self):
        # Arrange
        sleep_mock = MagicMock()
        detect_mock = MagicMock()
        with patch("stack_pr_poll.gh_stack.sync", return_value=("error", "conflict")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=True), \
             patch("stack_pr_poll.detect_next_stack_event", detect_mock):
            # Act
            result = poll(sleep=sleep_mock)

        # Assert
        assert result == "conflict"
        detect_mock.assert_not_called()
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — a review_comment/ci_failure event from the detector is returned
# immediately, without sleeping
# ---------------------------------------------------------------------------

class TestPollActionableEventFiresImmediately:
    @pytest.mark.parametrize(
        "detector_event, expected_result",
        [
            pytest.param(
                {"type": "review_comment", "task_work_item_id": "ADR-50"},
                {"task_work_item_id": "ADR-50", "event": "review_comment"},
                id="review_comment",
            ),
            pytest.param(
                {"type": "ci_failure", "task_work_item_id": "ADR-51"},
                {"task_work_item_id": "ADR-51", "event": "ci_failure"},
                id="ci_failure",
            ),
            pytest.param(
                {"type": "human_comment", "task_work_item_id": "ADR-54"},
                {"task_work_item_id": "ADR-54", "event": "human_comment"},
                id="human_comment",
            ),
        ],
    )
    def test_poll_actionable_event_renames_type_key_to_event_without_sleeping(
        self, detector_event, expected_result
    ):
        # Arrange
        sleep_mock = MagicMock()
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", return_value=detector_event):
            # Act
            result = poll(sleep=sleep_mock)

        # Assert
        assert result == expected_result
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — a task_merged event is untracked silently and the loop continues,
# unless every branch in the stack is now merged
# ---------------------------------------------------------------------------

class TestPollTaskMergedEvent:
    def test_poll_task_merged_not_every_branch_merged_continues_looping_to_no_change(self):
        # Arrange
        elapsed = [0.0]
        clock = lambda: elapsed[0]  # noqa: E731
        sleep_mock = MagicMock(side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
        merged_event = {"type": "task_merged", "task_work_item_id": "ADR-52"}
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", return_value=merged_event), \
             patch("stack_pr_poll._stack_complete", return_value=False):
            # Act
            result = poll(max_seconds=90, sleep=sleep_mock, clock=clock)

        # Assert
        assert result == "no_change"
        assert sleep_mock.call_count > 0

    def test_poll_task_merged_every_branch_merged_returns_stack_complete(self):
        # Arrange
        sleep_mock = MagicMock()
        merged_event = {"type": "task_merged", "task_work_item_id": "ADR-52"}
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", return_value=merged_event), \
             patch("stack_pr_poll._stack_complete", return_value=True):
            # Act
            result = poll(sleep=sleep_mock)

        # Assert
        assert result == "stack_complete"
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — nothing fired: loops until max_seconds elapses, then returns
# "no_change"; max_seconds=0 returns "no_change" immediately without sleeping
# ---------------------------------------------------------------------------

class TestPollNoChange:
    def test_poll_no_event_loops_until_max_seconds_then_returns_no_change(self):
        # Arrange
        elapsed = [0.0]
        clock = lambda: elapsed[0]  # noqa: E731
        sleep_mock = MagicMock(side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", return_value=None):
            # Act
            result = poll(max_seconds=90, sleep=sleep_mock, clock=clock)

        # Assert
        assert result == "no_change"

    def test_poll_max_seconds_zero_no_event_returns_no_change_without_sleeping(self):
        # Arrange
        sleep_mock = MagicMock()
        clock_mock = MagicMock(return_value=0.0)
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", return_value=None):
            # Act
            result = poll(max_seconds=0, sleep=sleep_mock, clock=clock_mock)

        # Assert
        assert result == "no_change"
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — sync runs every iteration, including iterations that loop past a
# quiet detector call
# ---------------------------------------------------------------------------

class TestPollSyncRunsEveryIteration:
    def test_poll_sync_called_once_per_loop_iteration(self):
        # Arrange
        sync_mock = MagicMock(return_value=("ok", ""))
        sleep_mock = MagicMock()
        clock_mock = MagicMock(return_value=0.0)
        detect_mock = MagicMock(
            side_effect=[None, None, {"type": "ci_failure", "task_work_item_id": "ADR-53"}]
        )
        with patch("stack_pr_poll.gh_stack.sync", sync_mock), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", detect_mock):
            # Act
            result = poll(max_seconds=999, sleep=sleep_mock, clock=clock_mock)

        # Assert
        assert result == {"task_work_item_id": "ADR-53", "event": "ci_failure"}
        assert sync_mock.call_count == 3


# ---------------------------------------------------------------------------
# poll — two conditions firing in the same window: only the first (by stack
# position, i.e. whatever the detector itself reports first) is returned by
# one call; the second is picked up on the very next, independent call
# ---------------------------------------------------------------------------

class TestPollSecondEventPickedUpOnNextCall:
    def test_poll_second_event_is_returned_on_a_separate_subsequent_call(self):
        # Arrange
        first_event = {"type": "review_comment", "task_work_item_id": "ADR-54"}
        second_event = {"type": "ci_failure", "task_work_item_id": "ADR-55"}
        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", side_effect=[first_event]):
            # Act
            first_result = poll(sleep=MagicMock())

        with patch("stack_pr_poll.gh_stack.sync", return_value=("ok", "")), \
             patch("stack_pr_poll._rebase_in_progress", return_value=False), \
             patch("stack_pr_poll.detect_next_stack_event", side_effect=[second_event]):
            # Act
            second_result = poll(sleep=MagicMock())

        # Assert
        assert first_result == {"task_work_item_id": "ADR-54", "event": "review_comment"}
        assert second_result == {"task_work_item_id": "ADR-55", "event": "ci_failure"}


# ---------------------------------------------------------------------------
# _rebase_in_progress — resolves the worktree's own git-dir (absolute or
# relative) and checks it for a mid-rebase marker directory
# ---------------------------------------------------------------------------

class TestRebaseInProgress:
    def test_rebase_in_progress_absolute_git_dir_with_rebase_merge_returns_true(self, tmp_path):
        # Arrange
        git_dir = tmp_path / ".git"
        (git_dir / "rebase-merge").mkdir(parents=True)
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout=str(git_dir) + "\n", stderr=""),
        ):
            # Act
            result = _rebase_in_progress(tmp_path)

        # Assert
        assert result is True

    def test_rebase_in_progress_relative_git_dir_with_rebase_apply_returns_true(self, tmp_path):
        # Arrange
        (tmp_path / ".git" / "rebase-apply").mkdir(parents=True)
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout=".git\n", stderr=""),
        ):
            # Act
            result = _rebase_in_progress(tmp_path)

        # Assert
        assert result is True

    def test_rebase_in_progress_no_marker_directories_returns_false(self, tmp_path):
        # Arrange
        (tmp_path / ".git").mkdir(parents=True)
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout=".git\n", stderr=""),
        ):
            # Act
            result = _rebase_in_progress(tmp_path)

        # Assert
        assert result is False

    def test_rebase_in_progress_git_dir_lookup_fails_returns_false(self, tmp_path):
        # Arrange
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=128, stdout="", stderr="not a git repository"),
        ):
            # Act
            result = _rebase_in_progress(tmp_path)

        # Assert
        assert result is False


# ---------------------------------------------------------------------------
# _stack_complete — every branch reported by gh_stack.view() is merged
# ---------------------------------------------------------------------------

class TestStackComplete:
    @pytest.mark.parametrize(
        "view_result, expected",
        [
            pytest.param(("error", "boom"), False, id="view_errors"),
            pytest.param(("ok", {"branches": []}), False, id="no_branches"),
            pytest.param(
                ("ok", {"branches": [{"isMerged": True}, {"isMerged": True}]}),
                True,
                id="every_branch_merged",
            ),
            pytest.param(
                ("ok", {"branches": [{"isMerged": True}, {"isMerged": False}]}),
                False,
                id="one_branch_not_merged",
            ),
        ],
    )
    def test_stack_complete_reflects_whether_every_branch_is_merged(self, tmp_path, view_result, expected):
        # Arrange
        with patch("stack_pr_poll.gh_stack.view", return_value=view_result):
            # Act
            result = _stack_complete(tmp_path)

        # Assert
        assert result is expected


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_no_change_result_prints_no_change(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_pr_poll.py", "0"])

        with patch("stack_pr_poll.poll", return_value="no_change"):
            # Act
            main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == "no_change"

    def test_main_dict_result_prints_result_json(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_pr_poll.py", "480"])
        event = {"task_work_item_id": "ADR-56", "event": "ci_failure"}

        with patch("stack_pr_poll.poll", return_value=event):
            # Act
            main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == event

    def test_main_poll_raises_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["stack_pr_poll.py", "480"])

        with patch("stack_pr_poll.poll", side_effect=RuntimeError("boom")):
            # Act
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Error: could not poll stack events: boom\n"
