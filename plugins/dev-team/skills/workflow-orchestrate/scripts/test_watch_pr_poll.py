"""Tests for watch_pr_poll.py — poll() (a bounded polling loop over
pr_event_detector.detect_pr_events()) and its CLI wrapper main().

Covers:
- poll: immediate event fire (no sleep), looping through empty checks before an eventual event,
  "no_change" once max_seconds elapses, "no_change" immediately for max_seconds=0, and
  multiple simultaneous event types passed through unchanged
- main() CLI wrapper: fired-event-list success, "no_change" success, and the error path
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from watch_pr_poll import main, poll

SCRIPTS_DIR = Path(__file__).parent


class TestPollEventFiresImmediately:
    @pytest.mark.parametrize(
        "events",
        [
            pytest.param(["review_comment"], id="single_event"),
            pytest.param(
                ["ci_failure", "base_updated", "review_comment"], id="multiple_events"
            ),
        ],
    )
    def test_poll_event_fires_immediately_returns_event_list_without_sleeping(self, events):
        # Arrange
        sleep_mock = MagicMock()
        with patch("watch_pr_poll.detect_pr_events", return_value=events):
            # Act
            result = poll("ADR-311", sleep=sleep_mock)

        # Assert
        assert result == events
        sleep_mock.assert_not_called()


class TestPollLoopsUntilEventFires:
    def test_poll_two_empty_checks_then_event_returns_event_list(self):
        # Arrange
        sleep_mock = MagicMock()
        clock_mock = MagicMock(return_value=0.0)
        with patch("watch_pr_poll.detect_pr_events", side_effect=[[], [], ["ci_failure"]]):
            # Act
            result = poll("ADR-311", sleep=sleep_mock, clock=clock_mock)

        # Assert
        assert result == ["ci_failure"]
        assert sleep_mock.call_count == 2


class TestPollNoChangeAtMaxSeconds:
    def test_poll_max_seconds_elapsed_with_no_events_returns_no_change(self):
        # Arrange
        elapsed = [0.0]
        clock = lambda: elapsed[0]  # noqa: E731
        sleep_mock = MagicMock(side_effect=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
        with patch("watch_pr_poll.detect_pr_events", return_value=[]):
            # Act
            result = poll("ADR-311", max_seconds=90, sleep=sleep_mock, clock=clock)

        # Assert
        assert result == "no_change"


class TestPollZeroMaxSeconds:
    def test_poll_max_seconds_zero_with_no_events_returns_no_change_without_sleeping(self):
        # Arrange
        sleep_mock = MagicMock()
        clock_mock = MagicMock(return_value=0.0)
        with patch("watch_pr_poll.detect_pr_events", return_value=[]):
            # Act
            result = poll("ADR-311", max_seconds=0, sleep=sleep_mock, clock=clock_mock)

        # Assert
        assert result == "no_change"
        sleep_mock.assert_not_called()


class TestMainCliWrapper:
    def test_main_no_context_file_and_zero_max_seconds_prints_no_change(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "watch_pr_poll.py"), "ADR-999", "0"],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert json.loads(result.stdout) == "no_change"

    def test_main_fired_event_list_prints_event_list_json(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["watch_pr_poll.py", "ADR-311", "480"])

        with patch("watch_pr_poll.poll", return_value=["ci_failure", "review_comment"]):
            # Act
            main()

        # Assert
        captured = capsys.readouterr()
        assert json.loads(captured.out) == ["ci_failure", "review_comment"]

    def test_main_poll_raises_prints_error_and_exits_1(self, monkeypatch, capsys):
        # Arrange
        monkeypatch.setattr(sys, "argv", ["watch_pr_poll.py", "ADR-311", "480"])

        with patch("watch_pr_poll.poll", side_effect=RuntimeError("boom")):
            # Act
            with pytest.raises(SystemExit) as exc_info:
                main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Error: could not poll PR events for 'ADR-311': boom\n"
