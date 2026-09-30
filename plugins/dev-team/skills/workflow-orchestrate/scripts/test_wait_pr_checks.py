"""Tests for wait_pr_checks.py.

Covers:
- _is_no_checks_error(): case-insensitive matching of gh pr checks' "zero checks" wording.
- _get_checks(): real success, a genuine query failure (_fail(), process exit), and the
  zero-checks case (returns None rather than failing).
- _get_checks_with_zero_check_retries(): immediate success, retries then success, and retries
  exhausted (still None) — #206's retry-before-blessing-as-"no CI" behavior.
- main(): the zero-checks-after-retries path treats it as a pass; a genuine query error still
  fails immediately with no retry.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# _is_no_checks_error
# ---------------------------------------------------------------------------

class TestIsNoChecksError:
    @pytest.mark.parametrize("detail", [
        "no checks reported on the 'main' branch",
        "No Checks Reported",
        "no status checks were found for this ref",
    ])
    def test_matches_known_wordings(self, detail):
        from wait_pr_checks import _is_no_checks_error
        assert _is_no_checks_error(detail) is True

    @pytest.mark.parametrize("detail", [
        "authentication required",
        "network error: connection refused",
        "unknown pull request",
    ])
    def test_does_not_match_genuine_errors(self, detail):
        from wait_pr_checks import _is_no_checks_error
        assert _is_no_checks_error(detail) is False


# ---------------------------------------------------------------------------
# _get_checks
# ---------------------------------------------------------------------------

class TestGetChecks:
    def test_returns_parsed_checks_on_success(self):
        from wait_pr_checks import _get_checks
        result = _completed(0, stdout=json.dumps([{"bucket": "pass"}]))
        with patch("subprocess.run", return_value=result):
            assert _get_checks("https://github.com/org/repo/pull/1") == [{"bucket": "pass"}]

    def test_returns_none_when_zero_checks_reported(self):
        from wait_pr_checks import _get_checks
        result = _completed(1, stderr="no checks reported on the 'main' branch")
        with patch("subprocess.run", return_value=result):
            assert _get_checks("https://github.com/org/repo/pull/1") is None

    def test_returns_none_when_json_output_is_an_empty_list(self):
        """Exit 0 with a genuinely empty JSON array is the same "nothing registered" shape."""
        from wait_pr_checks import _get_checks
        result = _completed(0, stdout="[]")
        with patch("subprocess.run", return_value=result):
            assert _get_checks("https://github.com/org/repo/pull/1") is None

    def test_calls_fail_on_a_genuine_error(self):
        from wait_pr_checks import _get_checks
        result = _completed(1, stderr="authentication required")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(SystemExit) as exc_info:
                _get_checks("https://github.com/org/repo/pull/1")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# _get_checks_with_zero_check_retries
# ---------------------------------------------------------------------------

class TestGetChecksWithZeroCheckRetries:
    def test_returns_immediately_when_checks_already_present(self):
        from wait_pr_checks import _get_checks_with_zero_check_retries
        with patch("wait_pr_checks._get_checks", return_value=[{"bucket": "pass"}]) as mock_get:
            with patch("time.sleep") as mock_sleep:
                result = _get_checks_with_zero_check_retries("https://github.com/org/repo/pull/1")
        assert result == [{"bucket": "pass"}]
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()

    def test_retries_then_succeeds(self):
        from wait_pr_checks import _get_checks_with_zero_check_retries
        with patch("wait_pr_checks._get_checks", side_effect=[None, [{"bucket": "pending"}]]) as mock_get:
            with patch("time.sleep") as mock_sleep:
                result = _get_checks_with_zero_check_retries("https://github.com/org/repo/pull/1")
        assert result == [{"bucket": "pending"}]
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()

    def test_gives_up_after_max_attempts_still_none(self):
        from wait_pr_checks import _get_checks_with_zero_check_retries, ZERO_CHECKS_MAX_ATTEMPTS
        with patch("wait_pr_checks._get_checks", return_value=None) as mock_get:
            with patch("time.sleep"):
                result = _get_checks_with_zero_check_retries("https://github.com/org/repo/pull/1")
        assert result is None
        assert mock_get.call_count == ZERO_CHECKS_MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# main() — end to end (in-process, subprocess.run mocked)
# ---------------------------------------------------------------------------

class TestMain:
    def test_zero_checks_after_retries_is_reported_as_passed(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["wait_pr_checks.py", "https://github.com/org/repo/pull/1"])
        import wait_pr_checks
        result = _completed(1, stderr="no checks reported on the 'main' branch")
        with patch("subprocess.run", return_value=result):
            with patch("time.sleep"):
                wait_pr_checks.main()

        captured = capsys.readouterr()
        last_line = captured.out.strip().splitlines()[-1]
        assert json.loads(last_line) == {"status": "passed", "note": "no checks configured"}

    def test_genuine_query_error_fails_without_retrying(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["wait_pr_checks.py", "https://github.com/org/repo/pull/1"])
        import wait_pr_checks
        result = _completed(1, stderr="authentication required")
        with patch("subprocess.run", return_value=result) as mock_run:
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(SystemExit) as exc_info:
                    wait_pr_checks.main()

        assert exc_info.value.code == 1
        mock_sleep.assert_not_called()
        assert mock_run.call_count == 1
        captured = capsys.readouterr()
        last_line = captured.out.strip().splitlines()[-1]
        assert json.loads(last_line) == {
            "status": "failed", "reason": "failed to query PR checks: authentication required",
        }

    def test_all_checks_passing_is_reported_as_passed(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["wait_pr_checks.py", "https://github.com/org/repo/pull/1"])
        import wait_pr_checks
        result = _completed(0, stdout=json.dumps([{"bucket": "pass"}, {"bucket": "pass"}]))
        with patch("subprocess.run", return_value=result):
            with patch("time.sleep"):
                wait_pr_checks.main()

        captured = capsys.readouterr()
        last_line = captured.out.strip().splitlines()[-1]
        assert json.loads(last_line) == {"status": "passed"}
