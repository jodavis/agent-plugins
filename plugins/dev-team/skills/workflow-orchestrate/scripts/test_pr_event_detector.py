"""Tests for pr_event_detector.py — detect_pr_events() determines which of the three monitor
conditions (review_comment, ci_failure, task_merged) have newly fired for a task's PR, given its
own context file and the current GitHub/git state. base_updated and dependency_merged have been
retired — they are subsumed by `gh stack sync` — see test_detect_next_stack_event.py.
"""

import json
import re
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# detect_pr_events — no context file yet for this task
# ---------------------------------------------------------------------------

class TestDetectPrEventsNoContextFile:
    def test_detect_pr_events_no_context_file_returns_empty_list_without_gh_calls(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from pr_event_detector import detect_pr_events

        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# detect_pr_events — context file exists but has no pr_url yet
# ---------------------------------------------------------------------------

class TestDetectPrEventsNoPrUrl:
    def test_detect_pr_events_context_file_exists_without_pr_url_returns_empty_list_without_gh_calls(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(work_item_id="ADR-999", pr_url="").save(path)

        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# detect_pr_events — a single new signal fires its matching event, unless it's
# already been recorded as seen
# ---------------------------------------------------------------------------

class TestDetectPrEventsSingleSignal:
    @pytest.mark.parametrize(
        "comments_json, checks_json, pr_view_json, extra_frontmatter, expected_events",
        [
            pytest.param(
                json.dumps([{"id": 101}, {"id": 205}]),
                json.dumps([]),
                json.dumps({"state": "OPEN", "baseRefName": "main"}),
                {},
                ["review_comment"],
                id="new_review_comment",
            ),
            pytest.param(
                json.dumps([]),
                json.dumps([{"bucket": "pass"}, {"bucket": "fail"}]),
                json.dumps({"state": "OPEN", "baseRefName": "main"}),
                {},
                ["ci_failure"],
                id="ci_checks_failing",
            ),
            pytest.param(
                json.dumps([]),
                json.dumps([]),
                json.dumps({"state": "MERGED", "baseRefName": "main"}),
                {},
                ["task_merged"],
                id="own_pr_merged",
            ),
            pytest.param(
                json.dumps([{"id": 101}, {"id": 205}]),
                json.dumps([]),
                json.dumps({"state": "OPEN", "baseRefName": "main"}),
                {"last_seen_review_comment_id": "205"},
                [],
                id="review_comment_max_id_already_seen",
            ),
            pytest.param(
                json.dumps([]),
                "no checks reported",
                json.dumps({"state": "OPEN", "baseRefName": "main"}),
                {},
                [],
                id="ci_checks_output_not_json_treated_as_no_checks",
            ),
            pytest.param(
                json.dumps([]),
                json.dumps([{"bucket": "fail"}]),
                json.dumps({"state": "OPEN", "baseRefName": "main"}),
                {"last_seen_ci_conclusion": "failing"},
                [],
                id="ci_still_failing_already_seen",
            ),
        ],
    )
    def test_detect_pr_events_single_signal_fires_matching_event(
        self, tmp_path, monkeypatch, comments_json, checks_json, pr_view_json, extra_frontmatter, expected_events
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-999",
            pr_url="https://github.com/acme/widget/pull/57",
            extra_frontmatter=extra_frontmatter,
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=comments_json, stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=checks_json, stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(returncode=0, stdout=pr_view_json, stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == expected_events


# ---------------------------------------------------------------------------
# detect_pr_events — a gh call other than the CI-checks call returns non-JSON
# output (e.g. a transient rate-limit or network blip): the affected signal is
# skipped rather than raising an unhandled JSONDecodeError out of the detector
# ---------------------------------------------------------------------------

class TestDetectPrEventsReviewCommentsOutputNotJson:
    def test_detect_pr_events_review_comments_output_not_json_skips_review_comment_signal(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-999",
            pr_url="https://github.com/acme/widget/pull/57",
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=1, stdout="", stderr="rate limited")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "main"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []


class TestDetectPrEventsOwnPrViewOutputNotJson:
    def test_detect_pr_events_own_pr_view_output_not_json_skips_task_merged_signal(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-999",
            pr_url="https://github.com/acme/widget/pull/57",
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(returncode=1, stdout="", stderr="rate limited")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# detect_pr_events — nothing new happened: a quiet call must leave the saved
# context file untouched
# ---------------------------------------------------------------------------

class TestDetectPrEventsQuietCall:
    def test_detect_pr_events_no_signals_changed_returns_empty_list_and_leaves_context_file_unchanged(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-999",
            pr_url="https://github.com/acme/widget/pull/57",
            extra_frontmatter={"last_seen_review_comment_id": "205"},
        ).save(path)
        text_before = path.read_text()

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([{"id": 205}]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "main"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []
        assert path.read_text() == text_before


# ---------------------------------------------------------------------------
# detect_pr_events — task_merged has no persisted "already reported" field
# (unlike review_comment/ci_failure/dependency_merged, which each derive
# idempotency from a recorded field); a merged PR is a terminal state, so
# task_merged fires on every call for as long as the PR stays merged. This
# documents that behavior explicitly rather than leaving it untested.
# ---------------------------------------------------------------------------

class TestDetectPrEventsTaskMergedCalledAgain:
    def test_detect_pr_events_task_merged_still_fires_on_a_second_call(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-999",
            pr_url="https://github.com/acme/widget/pull/57",
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "MERGED", "baseRefName": "main"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            first_result = detect_pr_events("ADR-999")
            second_result = detect_pr_events("ADR-999")

        # Assert
        assert first_result == ["task_merged"]
        assert second_result == ["task_merged"]


# ---------------------------------------------------------------------------
# detect_pr_events — pr_url doesn't match the expected GitHub PR URL shape:
# raise a clear diagnostic instead of a confusing AttributeError from
# `.match(...).groups()` on a None match
# ---------------------------------------------------------------------------

class TestDetectPrEventsMalformedPrUrl:
    def test_detect_pr_events_malformed_pr_url_raises_value_error_naming_the_url(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from pr_event_detector import detect_pr_events

        malformed_pr_url = "https://github.com/acme/widget/pull/57/"
        path = compute_context_path("ADR-999", get_repo_slug())
        PipelineContext(work_item_id="ADR-999", pr_url=malformed_pr_url).save(path)

        # Act / Assert
        with pytest.raises(ValueError, match=re.escape(malformed_pr_url)):
            detect_pr_events("ADR-999")

