"""Tests for pr_event_detector.py — detect_pr_events() determines which of the five monitor
conditions (review_comment, ci_failure, base_updated, dependency_merged, task_merged) have newly
fired for a task's PR, given its own context file and the current GitHub/git state.
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
# detect_pr_events — the base branch's remote tip moves past the recorded sha,
# alone or together with another signal firing in the same call, unless the
# remote lookup itself fails
# ---------------------------------------------------------------------------

class TestDetectPrEventsBaseUpdated:
    @pytest.mark.parametrize(
        "comments_json, ls_remote_returncode, ls_remote_stdout, ls_remote_stderr, expected_events",
        [
            pytest.param(
                json.dumps([]),
                0,
                "newsha456\trefs/heads/main\n",
                "",
                ["base_updated"],
                id="base_updated_only",
            ),
            pytest.param(
                json.dumps([{"id": 101}, {"id": 205}]),
                0,
                "newsha456\trefs/heads/main\n",
                "",
                ["review_comment", "base_updated"],
                id="review_comment_and_base_updated_together",
            ),
            pytest.param(
                json.dumps([]),
                1,
                "",
                "fatal: repository not found",
                [],
                id="remote_lookup_fails_skips_base_updated",
            ),
            pytest.param(
                json.dumps([]),
                0,
                "oldsha123\trefs/heads/main\n",
                "",
                [],
                id="base_sha_unchanged_no_refire",
            ),
        ],
    )
    def test_detect_pr_events_base_branch_tip_changed_fires_base_updated(
        self,
        tmp_path,
        monkeypatch,
        comments_json,
        ls_remote_returncode,
        ls_remote_stdout,
        ls_remote_stderr,
        expected_events,
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
            extra_frontmatter={"base_branch": "main", "base_branch_sha": "oldsha123"},
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=comments_json, stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "main"}), stderr=""
                )
            if cmd[:2] == ["git", "ls-remote"]:
                return MagicMock(
                    returncode=ls_remote_returncode, stdout=ls_remote_stdout, stderr=ls_remote_stderr
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == expected_events


# ---------------------------------------------------------------------------
# detect_pr_events — no baseline sha recorded yet: the first observation just
# records it, without firing base_updated
# ---------------------------------------------------------------------------

class TestDetectPrEventsBaseUpdatedFirstObservation:
    def test_detect_pr_events_base_branch_sha_not_yet_recorded_records_baseline_without_firing(
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
            extra_frontmatter={"base_branch": "main"},
        ).save(path)

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "main"}), stderr=""
                )
            if cmd[:2] == ["git", "ls-remote"]:
                return MagicMock(returncode=0, stdout="abcsha111\trefs/heads/main\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-999")

        # Assert
        assert result == []
        reloaded = PipelineContext.load(path)
        assert reloaded.extra_frontmatter.get("base_branch_sha") == "abcsha111"


# ---------------------------------------------------------------------------
# detect_pr_events — a declared dependency's PR has merged onto a new target branch,
# firing dependency_merged only when that target hasn't already been recorded
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyMerged:
    @pytest.mark.parametrize(
        "existing_extra_frontmatter, expected_events",
        [
            pytest.param({}, ["dependency_merged"], id="not_yet_recorded"),
            pytest.param(
                {"base_branch": "new-base", "base_branch_sha": "mergedsha789"},
                [],
                id="already_recorded",
            ),
        ],
    )
    def test_detect_pr_events_dependency_pr_merged_onto_new_target_fires_only_when_not_already_recorded(
        self, tmp_path, monkeypatch, existing_extra_frontmatter, expected_events
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(
            "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
            "\n"
            "**Depends on:** ADR-2\n"
            "\n"
            "### [ADR-2: Title Two](https://example.com/ADR-2) \U0001F916\n"
            "\n"
            "**Depends on:** — none —\n"
        )

        repo_slug = get_repo_slug()
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
            extra_frontmatter=existing_extra_frontmatter,
        ).save(compute_context_path("ADR-1", repo_slug))
        PipelineContext(
            work_item_id="ADR-2",
            pr_url="https://github.com/acme/widget/pull/99",
        ).save(compute_context_path("ADR-2", repo_slug))

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                if cmd[3] == "https://github.com/acme/widget/pull/99":
                    return MagicMock(
                        returncode=0,
                        stdout=json.dumps({"state": "MERGED", "baseRefName": "new-base"}),
                        stderr="",
                    )
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "old-base"}), stderr=""
                )
            if cmd[:2] == ["git", "ls-remote"]:
                return MagicMock(returncode=0, stdout="mergedsha789\trefs/heads/new-base\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

        # Assert
        assert result == expected_events


# ---------------------------------------------------------------------------
# detect_pr_events — the stacked/out-of-order case: a dependency's PR merges onto
# another still-open task's own working branch, not a hardcoded feature branch
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyMergedReportsActualBranch:
    def test_detect_pr_events_dependency_merged_onto_another_tasks_working_branch_reports_that_branch(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(
            "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
            "\n"
            "**Depends on:** ADR-2\n"
            "\n"
            "### [ADR-2: Title Two](https://example.com/ADR-2) \U0001F916\n"
            "\n"
            "**Depends on:** — none —\n"
        )

        repo_slug = get_repo_slug()
        path = compute_context_path("ADR-1", repo_slug)
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
        ).save(path)
        PipelineContext(
            work_item_id="ADR-2",
            pr_url="https://github.com/acme/widget/pull/99",
        ).save(compute_context_path("ADR-2", repo_slug))

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                if cmd[3] == "https://github.com/acme/widget/pull/99":
                    return MagicMock(
                        returncode=0,
                        stdout=json.dumps({"state": "MERGED", "baseRefName": "dev/claude/ADR-7"}),
                        stderr="",
                    )
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "main"}), stderr=""
                )
            if cmd[:2] == ["git", "ls-remote"]:
                return MagicMock(returncode=0, stdout="stackedsha321\trefs/heads/dev/claude/ADR-7\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

        # Assert
        assert result == ["dependency_merged"]
        reloaded = PipelineContext.load(path)
        assert reloaded.extra_frontmatter.get("base_branch") == "dev/claude/ADR-7"


# ---------------------------------------------------------------------------
# detect_pr_events — a declared dependency with no context file yet is skipped,
# not treated as an error
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyMergedMissingContext:
    def test_detect_pr_events_dependency_without_context_file_skips_dependency_merged(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(
            "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
            "\n"
            "**Depends on:** ADR-2\n"
            "\n"
            "### [ADR-2: Title Two](https://example.com/ADR-2) \U0001F916\n"
            "\n"
            "**Depends on:** — none —\n"
        )

        repo_slug = get_repo_slug()
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
        ).save(compute_context_path("ADR-1", repo_slug))
        # ADR-2 (the dependency) intentionally has no context file at all.

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "old-base"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# detect_pr_events — a declared dependency whose context file exists but has no
# pr_url yet is skipped, not treated as an error
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyMergedNoPrUrl:
    def test_detect_pr_events_dependency_without_pr_url_skips_dependency_merged(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(
            "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
            "\n"
            "**Depends on:** ADR-2\n"
            "\n"
            "### [ADR-2: Title Two](https://example.com/ADR-2) \U0001F916\n"
            "\n"
            "**Depends on:** — none —\n"
        )

        repo_slug = get_repo_slug()
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
        ).save(compute_context_path("ADR-1", repo_slug))
        PipelineContext(
            work_item_id="ADR-2",
            pr_url="",
        ).save(compute_context_path("ADR-2", repo_slug))

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "old-base"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# detect_pr_events — a dependency's own `gh pr view` call returns non-JSON output:
# dependency_merged is skipped for that dependency rather than raising
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyPrViewOutputNotJson:
    def test_detect_pr_events_dependency_pr_view_output_not_json_skips_dependency_merged(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(
            "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
            "\n"
            "**Depends on:** ADR-2\n"
            "\n"
            "### [ADR-2: Title Two](https://example.com/ADR-2) \U0001F916\n"
            "\n"
            "**Depends on:** — none —\n"
        )

        repo_slug = get_repo_slug()
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
        ).save(compute_context_path("ADR-1", repo_slug))
        PipelineContext(
            work_item_id="ADR-2",
            pr_url="https://github.com/acme/widget/pull/99",
        ).save(compute_context_path("ADR-2", repo_slug))

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                if cmd[3] == "https://github.com/acme/widget/pull/99":
                    return MagicMock(returncode=1, stdout="", stderr="rate limited")
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "old-base"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

        # Assert
        assert result == []


# ---------------------------------------------------------------------------
# detect_pr_events — the dependency graph yields nothing to check for this task
# (no declared dependencies, or a spec that fails to parse), so dependency_merged
# is skipped silently rather than raising
# ---------------------------------------------------------------------------

class TestDetectPrEventsDependencyMergedNoDependenciesToCheck:
    @pytest.mark.parametrize(
        "spec_content",
        [
            pytest.param(
                "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
                "\n"
                "**Depends on:** — none —\n",
                id="no_declared_dependencies",
            ),
            pytest.param(
                # ADR-1 depends on ADR-99, but no ADR-99 heading exists — a dangling reference
                # that makes task_dependencies.parse_task_dependencies raise TaskDependencyError.
                "### [ADR-1: Title One](https://example.com/ADR-1) \U0001F916\n"
                "\n"
                "**Depends on:** ADR-99\n",
                id="unparseable_spec_dangling_reference",
            ),
        ],
    )
    def test_detect_pr_events_dependency_graph_yields_nothing_skips_dependency_merged(
        self, tmp_path, monkeypatch, spec_content
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import pr_event_detector
        from pr_event_detector import detect_pr_events

        monkeypatch.setattr(pr_event_detector, "REPO_ROOT", tmp_path)

        (tmp_path / "spec.md").write_text(spec_content)

        repo_slug = get_repo_slug()
        PipelineContext(
            work_item_id="ADR-1",
            pr_url="https://github.com/acme/widget/pull/57",
            spec_path="spec.md",
        ).save(compute_context_path("ADR-1", repo_slug))

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "view"]:
                return MagicMock(
                    returncode=0, stdout=json.dumps({"state": "OPEN", "baseRefName": "old-base"}), stderr=""
                )
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_pr_events("ADR-1")

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

