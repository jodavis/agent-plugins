"""Tests for pr_list_poll.py — poll() (a bounded polling loop over a fixed, explicit list of PR
numbers, with no `gh stack` involvement) and its CLI wrapper main().

Covers:
- poll: a review_comment/human_comment/ci_failure event for one PR checks out its head branch and
  returns immediately; a task_merged event drops that PR from the active set silently and the
  loop continues unless every given PR is now merged ("all_complete"); "no_change" once
  max_seconds elapses; a PR whose head-ref lookup fails is kept active (not dropped) and retried;
  a second, independent poll() call is unaffected by what the previous call returned
- _head_ref / _task_work_item_id: JSON parse failure, branch-name id extraction with and without
  a recognizable work-item-id prefix
- main() CLI wrapper: comma-separated PR number parsing, dict-result success, "no_change"
  success, and the error path (including an unparseable pr_numbers argument)
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from pr_list_poll import main, poll, _head_ref, _task_work_item_id


# ---------------------------------------------------------------------------
# poll — an actionable event for one PR checks out its branch and returns
# immediately, without sleeping
# ---------------------------------------------------------------------------

class TestPollActionableEventFiresImmediately:
    @pytest.mark.parametrize(
        "events, expected_event",
        [
            pytest.param(["review_comment"], "review_comment", id="review_comment"),
            pytest.param(["human_comment"], "human_comment", id="human_comment"),
            pytest.param(["ci_failure"], "ci_failure", id="ci_failure"),
        ],
    )
    def test_poll_actionable_event_checks_out_branch_and_returns_without_sleeping(
        self, events, expected_event
    ):
        # Arrange
        sleep_mock = MagicMock()
        checkout_mock = MagicMock(returncode=0)
        with patch("pr_list_poll._head_ref", return_value="dev/claude/ADR-50-slug"), \
             patch("pr_list_poll.detect_pr_events", return_value=events), \
             patch("subprocess.run", return_value=checkout_mock):
            # Act
            result = poll([50], sleep=sleep_mock)

        # Assert
        assert result == {"task_work_item_id": "ADR-50", "event": expected_event}
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — a task_merged event drops that PR silently and the loop continues,
# unless every given PR is now merged
# ---------------------------------------------------------------------------

class TestPollTaskMergedEvent:
    def test_poll_one_pr_merged_others_pending_continues_looping_to_no_change(self):
        # Arrange
        elapsed = [0.0]
        clock = lambda: elapsed[0]  # noqa: E731
        sleep_mock = MagicMock(side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))

        def fake_head_ref(pr_number, cwd):
            return f"dev/claude/ADR-5{pr_number}"

        def fake_detect(task_work_item_id):
            return ["task_merged"] if task_work_item_id == "ADR-52" else []

        with patch("pr_list_poll._head_ref", side_effect=fake_head_ref), \
             patch("pr_list_poll.detect_pr_events", side_effect=fake_detect):
            # Act
            result = poll([52, 53], max_seconds=90, sleep=sleep_mock, clock=clock)

        # Assert
        assert result == "no_change"
        assert sleep_mock.call_count > 0

    def test_poll_every_given_pr_merged_returns_all_complete(self):
        # Arrange
        sleep_mock = MagicMock()
        with patch("pr_list_poll._head_ref", return_value="dev/claude/ADR-52"), \
             patch("pr_list_poll.detect_pr_events", return_value=["task_merged"]):
            # Act
            result = poll([52], sleep=sleep_mock)

        # Assert
        assert result == "all_complete"
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — a head-ref lookup failure keeps the PR active (retried), never
# silently dropped
# ---------------------------------------------------------------------------

class TestPollHeadRefLookupFails:
    def test_poll_head_ref_lookup_fails_keeps_pr_active_until_max_seconds(self):
        # Arrange
        elapsed = [0.0]
        clock = lambda: elapsed[0]  # noqa: E731
        sleep_mock = MagicMock(side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
        detect_mock = MagicMock()
        with patch("pr_list_poll._head_ref", return_value=""), \
             patch("pr_list_poll.detect_pr_events", detect_mock):
            # Act
            result = poll([61], max_seconds=90, sleep=sleep_mock, clock=clock)

        # Assert
        assert result == "no_change"
        detect_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — nothing fired: loops until max_seconds elapses, then returns
# "no_change"; max_seconds=0 returns "no_change" immediately without sleeping
# ---------------------------------------------------------------------------

class TestPollNoChange:
    def test_poll_max_seconds_zero_no_event_returns_no_change_without_sleeping(self):
        # Arrange
        sleep_mock = MagicMock()
        clock_mock = MagicMock(return_value=0.0)
        with patch("pr_list_poll._head_ref", return_value="dev/claude/ADR-62"), \
             patch("pr_list_poll.detect_pr_events", return_value=[]):
            # Act
            result = poll([62], max_seconds=0, sleep=sleep_mock, clock=clock_mock)

        # Assert
        assert result == "no_change"
        sleep_mock.assert_not_called()


# ---------------------------------------------------------------------------
# poll — two conditions firing in the same window: only the first (by
# pr_numbers order) is returned by one call; the second is picked up on the
# very next, independent call
# ---------------------------------------------------------------------------

class TestPollSecondEventPickedUpOnNextCall:
    def test_poll_second_event_is_returned_on_a_separate_subsequent_call(self):
        # Arrange
        def fake_head_ref(pr_number, cwd):
            return f"dev/claude/ADR-{pr_number}"

        def fake_detect_first(task_work_item_id):
            return ["review_comment"] if task_work_item_id == "ADR-71" else []

        def fake_detect_second(task_work_item_id):
            return ["ci_failure"] if task_work_item_id == "ADR-72" else []

        with patch("pr_list_poll._head_ref", side_effect=fake_head_ref), \
             patch("pr_list_poll.detect_pr_events", side_effect=fake_detect_first), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            # Act
            first_result = poll([71, 72], sleep=MagicMock())

        with patch("pr_list_poll._head_ref", side_effect=fake_head_ref), \
             patch("pr_list_poll.detect_pr_events", side_effect=fake_detect_second), \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            # Act
            second_result = poll([72], sleep=MagicMock())

        # Assert
        assert first_result == {"task_work_item_id": "ADR-71", "event": "review_comment"}
        assert second_result == {"task_work_item_id": "ADR-72", "event": "ci_failure"}


# ---------------------------------------------------------------------------
# _head_ref — resolves headRefName from `gh pr view --json headRefName`
# ---------------------------------------------------------------------------

class TestHeadRef:
    def test_head_ref_parses_json_output(self, tmp_path):
        # Arrange
        run_result = MagicMock(stdout='{"headRefName": "dev/claude/ADR-80"}')
        with patch("subprocess.run", return_value=run_result):
            # Act
            result = _head_ref(80, tmp_path)

        # Assert
        assert result == "dev/claude/ADR-80"

    def test_head_ref_invalid_json_returns_empty_string(self, tmp_path):
        # Arrange
        run_result = MagicMock(stdout="not json")
        with patch("subprocess.run", return_value=run_result):
            # Act
            result = _head_ref(81, tmp_path)

        # Assert
        assert result == ""


# ---------------------------------------------------------------------------
# _task_work_item_id — extracts the work-item-id prefix from a branch's last
# path segment, falling back to the whole segment when it doesn't match
# ---------------------------------------------------------------------------

class TestTaskWorkItemId:
    @pytest.mark.parametrize(
        "head_ref, expected",
        [
            pytest.param("dev/claude/ADR-90-some-slug", "ADR-90", id="prefixed_with_slug"),
            pytest.param("dev/claude/ADR-91", "ADR-91", id="prefixed_no_slug"),
            pytest.param("some-nonstandard-branch", "some-nonstandard-branch", id="no_match_falls_back"),
        ],
    )
    def test_task_work_item_id_extraction(self, head_ref, expected):
        # Act
        result = _task_work_item_id(head_ref)

        # Assert
        assert result == expected


# ---------------------------------------------------------------------------
# main() CLI wrapper
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_parses_comma_separated_pr_numbers(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["pr_list_poll.py", "12,34, 56", "480"])

        with patch("pr_list_poll.poll", return_value="no_change") as poll_mock:
            # Act
            main()

        # Assert
        poll_mock.assert_called_once_with([12, 34, 56], 480)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == "no_change"

    def test_main_dict_result_prints_result_json(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["pr_list_poll.py", "56"])
        event = {"task_work_item_id": "ADR-56", "event": "ci_failure"}

        with patch("pr_list_poll.poll", return_value=event):
            # Act
            main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == event

    def test_main_unparseable_pr_numbers_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["pr_list_poll.py", "not-a-number"])

        # Act
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith("Error: could not parse PR numbers:")

    def test_main_poll_raises_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["pr_list_poll.py", "56"])

        with patch("pr_list_poll.poll", side_effect=RuntimeError("boom")):
            # Act
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Error: could not poll PR events: boom\n"
