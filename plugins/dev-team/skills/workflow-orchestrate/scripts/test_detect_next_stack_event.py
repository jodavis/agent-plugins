"""Tests for detect_next_stack_event.py — detect_next_stack_event(epic_id) scans a stack's
branches (via gh_stack.view(), already in stack-position order) and returns the first actionable
event across the whole stack — one of review_comment, ci_failure, or task_merged — or None if
nothing fired this call.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# detect_next_stack_event — a single new signal on the first (and only) branch's own PR
# fires its matching event, naming that branch's task
# ---------------------------------------------------------------------------

class TestDetectNextStackEventSingleSignal:
    @pytest.mark.parametrize(
        "work_item_id, pr_url, branch_name, is_merged, comments_json, checks_json, expected_type",
        [
            pytest.param(
                "ADR-50",
                "https://github.com/acme/widget/pull/57",
                "dev/claude/ADR-50",
                False,
                json.dumps([{"id": 101}]),
                json.dumps([]),
                "review_comment",
                id="new_review_comment",
            ),
            pytest.param(
                "ADR-51",
                "https://github.com/acme/widget/pull/58",
                "dev/claude/ADR-51",
                False,
                json.dumps([]),
                json.dumps([{"bucket": "fail"}]),
                "ci_failure",
                id="failing_ci_checks",
            ),
            pytest.param(
                "ADR-52",
                "https://github.com/acme/widget/pull/59",
                "dev/claude/ADR-52",
                True,
                json.dumps([]),
                json.dumps([]),
                "task_merged",
                id="branch_is_merged",
            ),
        ],
    )
    def test_detect_next_stack_event_single_signal_on_first_branch_fires_matching_event(
        self,
        tmp_path,
        monkeypatch,
        work_item_id,
        pr_url,
        branch_name,
        is_merged,
        comments_json,
        checks_json,
        expected_type,
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id=work_item_id,
            pr_url=pr_url,
        ).save(compute_context_path(work_item_id, get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {"branches": [{"name": branch_name, "isMerged": is_merged}]},
                )
            ),
        )

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=comments_json, stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=checks_json, stderr="")
            if cmd[:2] == ["git", "checkout"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result == {"type": expected_type, "task_work_item_id": work_item_id}


# ---------------------------------------------------------------------------
# detect_next_stack_event — a not-yet-merged branch whose context file has no pr_url yet
# is skipped for review/CI purposes without raising or making any gh calls
# ---------------------------------------------------------------------------

class TestDetectNextStackEventNoPrUrl:
    def test_detect_next_stack_event_branch_without_pr_url_is_skipped_without_gh_calls(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id="ADR-53",
            pr_url="",
        ).save(compute_context_path("ADR-53", get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {"branches": [{"name": "dev/claude/ADR-53", "isMerged": False}]},
                )
            ),
        )

        mock_run = MagicMock()

        # Act
        with patch("subprocess.run", mock_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result is None
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# detect_next_stack_event — no branch in the stack has anything actionable:
# every PR is quiet and nothing is merged, so the scan returns None having
# still made the per-PR review/CI calls
# ---------------------------------------------------------------------------

class TestDetectNextStackEventNoneFired:
    def test_detect_next_stack_event_no_signals_across_whole_stack_returns_none(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id="ADR-60",
            pr_url="https://github.com/acme/widget/pull/70",
        ).save(compute_context_path("ADR-60", get_repo_slug()))
        PipelineContext(
            work_item_id="ADR-61",
            pr_url="https://github.com/acme/widget/pull/71",
        ).save(compute_context_path("ADR-61", get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {
                        "branches": [
                            {"name": "dev/claude/ADR-60", "isMerged": False},
                            {"name": "dev/claude/ADR-61", "isMerged": False},
                        ]
                    },
                )
            ),
        )

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result is None


# ---------------------------------------------------------------------------
# detect_next_stack_event — a review comment fires for a task other than the
# first branch scanned: the worktree is checked out onto *that* task's own
# branch, not the first branch in the stack
# ---------------------------------------------------------------------------

class TestDetectNextStackEventChecksOutFiringBranch:
    def test_detect_next_stack_event_second_branch_fires_checks_out_second_branch(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id="ADR-64",
            pr_url="https://github.com/acme/widget/pull/74",
        ).save(compute_context_path("ADR-64", get_repo_slug()))
        PipelineContext(
            work_item_id="ADR-65",
            pr_url="https://github.com/acme/widget/pull/75",
        ).save(compute_context_path("ADR-65", get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {
                        "branches": [
                            {"name": "dev/claude/ADR-64", "isMerged": False},
                            {"name": "dev/claude/ADR-65", "isMerged": False},
                        ]
                    },
                )
            ),
        )

        checkout_calls = []

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                if "74" in cmd[2]:
                    return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
                return MagicMock(returncode=0, stdout=json.dumps([{"id": 900}]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:2] == ["git", "checkout"]:
                checkout_calls.append(cmd)
                return MagicMock(returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result == {"type": "review_comment", "task_work_item_id": "ADR-65"}
        assert checkout_calls == [["git", "checkout", "dev/claude/ADR-65"]]


# ---------------------------------------------------------------------------
# detect_next_stack_event — two branches each have a firing event in the same
# call: only the first, by stack position, is reported; the second branch's
# own PR is never even queried
# ---------------------------------------------------------------------------

class TestDetectNextStackEventStackPositionPrecedence:
    def test_detect_next_stack_event_two_branches_fire_only_first_by_position_reported(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id="ADR-66",
            pr_url="https://github.com/acme/widget/pull/76",
        ).save(compute_context_path("ADR-66", get_repo_slug()))
        PipelineContext(
            work_item_id="ADR-67",
            pr_url="https://github.com/acme/widget/pull/77",
        ).save(compute_context_path("ADR-67", get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {
                        "branches": [
                            {"name": "dev/claude/ADR-66", "isMerged": False},
                            {"name": "dev/claude/ADR-67", "isMerged": False},
                        ]
                    },
                )
            ),
        )

        queried_prs = []

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                queried_prs.append(cmd[2])
                return MagicMock(returncode=0, stdout=json.dumps([{"id": 901}]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([{"bucket": "fail"}]), stderr="")
            if cmd[:2] == ["git", "checkout"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result == {"type": "review_comment", "task_work_item_id": "ADR-66"}
        assert not any("77" in pr for pr in queried_prs)


# ---------------------------------------------------------------------------
# detect_next_stack_event — a branch already reported as merged in a prior
# call never re-fires task_merged; the scan moves on to the next branch
# ---------------------------------------------------------------------------

class TestDetectNextStackEventMergedAlreadySeen:
    def test_detect_next_stack_event_merged_branch_already_seen_does_not_refire(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        import detect_next_stack_event

        PipelineContext(
            work_item_id="ADR-62",
            pr_url="https://github.com/acme/widget/pull/72",
            extra_frontmatter={"stack_task_merged_seen": "true"},
        ).save(compute_context_path("ADR-62", get_repo_slug()))
        PipelineContext(
            work_item_id="ADR-63",
            pr_url="https://github.com/acme/widget/pull/73",
        ).save(compute_context_path("ADR-63", get_repo_slug()))

        monkeypatch.setattr(
            detect_next_stack_event.gh_stack,
            "view",
            MagicMock(
                return_value=(
                    "ok",
                    {
                        "branches": [
                            {"name": "dev/claude/ADR-62", "isMerged": True},
                            {"name": "dev/claude/ADR-63", "isMerged": False},
                        ]
                    },
                )
            ),
        )

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["gh", "api"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            if cmd[:3] == ["gh", "pr", "checks"]:
                return MagicMock(returncode=0, stdout=json.dumps([]), stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        # Act
        with patch("subprocess.run", side_effect=fake_run):
            result = detect_next_stack_event.detect_next_stack_event("ADR-EPIC-1")

        # Assert
        assert result is None
