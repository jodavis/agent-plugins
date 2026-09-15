"""Tests for task_readiness.py — dependency_status() (a dependency task-work-item's own
context file translated into a coarse status), is_task_eligible() (whether a task is
eligible to start given its declared dependencies' statuses), and task_snapshot() (a task's
status plus the fields a caller needs to judge staleness without a second file read).

Covers:
- dependency_status: no context file, terminal states (done/failed), pr_url-implies-ready,
  and the in_progress fallback
- is_task_eligible: empty dependency list, single-dependency done/ready/not-started (all three
  short of "done" other than done itself return "waiting" — "ready" alone is no longer enough,
  since a dependency isn't guaranteed linked into the stack until it's fully `done`), every
  dependency done in any count, 2+ dependencies short of done, and a failed dependency
  short-circuiting to blocked. No `base_branch` is returned — no merge is ever required, but
  unlike ADR-374's original "ready or done" rule, an open PR alone is not enough either.
- task_snapshot: no context file yet, and an existing context file
- main() CLI wrapper: one narrow integration test covering the primary happy-path — a single
  ready dependency prints `{"status": "eligible", "base_branch": null}` on stdout, exit 0.
  `base_branch` is kept as an unconditional `null` in the CLI's JSON shape as a compatibility
  shim for `ensure-working-branch`'s still-unmigrated step 4b, which reads it but no longer
  branches meaningfully on it.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# dependency_status — no context file
# ---------------------------------------------------------------------------

class TestDependencyStatusNoContextFile:
    def test_dependency_status_no_context_file_returns_not_started(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import dependency_status

        # Act
        status = dependency_status("ADR-999")

        # Assert
        assert status == "not_started"


# ---------------------------------------------------------------------------
# dependency_status — terminal states take precedence
# ---------------------------------------------------------------------------

class TestDependencyStatusTerminalStates:
    @pytest.mark.parametrize(
        "context_state, expected_status",
        [
            pytest.param("done", "done", id="state_done"),
            pytest.param("failed", "failed", id="state_failed"),
        ],
    )
    def test_dependency_status_terminal_state_returns_matching_status(
        self, tmp_path, monkeypatch, context_state, expected_status
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import dependency_status

        path = compute_context_path("ADR-1", get_repo_slug())
        PipelineContext(work_item_id="ADR-1", state=context_state).save(path)

        # Act
        status = dependency_status("ADR-1")

        # Assert
        assert status == expected_status


# ---------------------------------------------------------------------------
# dependency_status — pr_url implies ready, when state is non-terminal
# ---------------------------------------------------------------------------

class TestDependencyStatusPrUrlSet:
    def test_dependency_status_pr_url_set_with_non_terminal_state_returns_ready(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import dependency_status

        path = compute_context_path("ADR-1", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-1", state="creating_pr", pr_url="https://github.com/example/repo/pull/1"
        ).save(path)

        # Act
        status = dependency_status("ADR-1")

        # Assert
        assert status == "ready"


# ---------------------------------------------------------------------------
# dependency_status — neither pr_url nor a terminal state
# ---------------------------------------------------------------------------

class TestDependencyStatusInProgress:
    def test_dependency_status_no_pr_url_and_non_terminal_state_returns_in_progress(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import dependency_status

        path = compute_context_path("ADR-1", get_repo_slug())
        PipelineContext(work_item_id="ADR-1", state="researching").save(path)

        # Act
        status = dependency_status("ADR-1")

        # Assert
        assert status == "in_progress"


# ---------------------------------------------------------------------------
# task_snapshot — no context file yet
# ---------------------------------------------------------------------------

class TestTaskSnapshotNoContextFile:
    def test_task_snapshot_no_context_file_returns_not_started_with_null_fields(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import task_snapshot

        # Act
        snapshot = task_snapshot("ADR-999")

        # Assert
        assert snapshot == {"status": "not_started", "last_updated": None, "worktree_path": None}


# ---------------------------------------------------------------------------
# task_snapshot — existing context file surfaces status, last_updated, worktree_path
# ---------------------------------------------------------------------------

class TestTaskSnapshotExistingContextFile:
    def test_task_snapshot_existing_context_file_returns_status_last_updated_and_worktree_path(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import task_snapshot

        path = compute_context_path("ADR-1", get_repo_slug())
        ctx = PipelineContext(
            work_item_id="ADR-1",
            state="creating-pr",
            pr_url="https://github.com/example/repo/pull/1",
            extra_frontmatter={"worktree_path": "/some/worktree/path"},
        )
        ctx.save(path)
        saved_ctx = PipelineContext.load(path)

        # Act
        snapshot = task_snapshot("ADR-1")

        # Assert
        assert snapshot == {
            "status": "ready",
            "last_updated": saved_ctx.last_updated.isoformat(),
            "worktree_path": "/some/worktree/path",
        }


# ---------------------------------------------------------------------------
# is_task_eligible — empty dependency list
# ---------------------------------------------------------------------------

class TestIsTaskEligibleEmptyDependencies:
    def test_is_task_eligible_empty_dependency_ids_returns_eligible(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import is_task_eligible

        # Act
        result = is_task_eligible("ADR-1", [])

        # Assert
        assert result == "eligible"


# ---------------------------------------------------------------------------
# is_task_eligible — single dependency, done vs. ready-but-not-done vs. in-progress. Ready alone
# is no longer enough — only "done" (signed off and linked into the stack) makes it eligible.
# ---------------------------------------------------------------------------

class TestIsTaskEligibleSingleDependency:
    @pytest.mark.parametrize(
        "dep_context_kwargs, expected_result",
        [
            pytest.param(
                dict(state="done"),
                "eligible",
                id="done_returns_eligible",
            ),
            pytest.param(
                dict(state="creating_pr", pr_url="https://github.com/example/repo/pull/2"),
                "waiting",
                id="ready_but_not_done_returns_waiting",
            ),
            pytest.param(
                dict(state="researching"),
                "waiting",
                id="in_progress_returns_waiting",
            ),
        ],
    )
    def test_is_task_eligible_single_dependency_returns_expected_result(
        self, tmp_path, monkeypatch, dep_context_kwargs, expected_result
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        dep_path = compute_context_path("ADR-2", get_repo_slug())
        PipelineContext(work_item_id="ADR-2", **dep_context_kwargs).save(dep_path)

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2"])

        # Assert
        assert result == expected_result


# ---------------------------------------------------------------------------
# is_task_eligible — single dependency, not started at all (no context file)
# ---------------------------------------------------------------------------

class TestIsTaskEligibleSingleDependencyNotStarted:
    def test_is_task_eligible_single_dependency_not_started_returns_waiting(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import is_task_eligible

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2"])

        # Assert
        assert result == "waiting"


# ---------------------------------------------------------------------------
# is_task_eligible — every dependency done, any count, is eligible. No merge is ever required,
# and no "all but one" exception exists — but a mix including a merely-"ready" (not yet "done")
# dependency is still "waiting", since an open PR alone doesn't guarantee it's linked into the
# stack yet.
# ---------------------------------------------------------------------------

class TestIsTaskEligibleAllDone:
    def test_is_task_eligible_two_dependencies_all_done_returns_eligible(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state="done").save(compute_context_path("ADR-2", repo_slug))
        PipelineContext(work_item_id="ADR-3", state="done").save(compute_context_path("ADR-3", repo_slug))

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == "eligible"


# ---------------------------------------------------------------------------
# is_task_eligible — two or more dependencies short of done (including one merely "ready")
# ---------------------------------------------------------------------------

class TestIsTaskEligibleTwoOrMoreNotDone:
    @pytest.mark.parametrize(
        "dep2_state, dep2_extra, dep3_state, dep3_extra",
        [
            pytest.param(
                "researching", {},
                "planning", {},
                id="neither_done_nor_ready_returns_waiting",
            ),
            pytest.param(
                "done", {},
                "creating_pr", {"pr_url": "https://github.com/example/repo/pull/3"},
                id="one_done_one_merely_ready_returns_waiting",
            ),
            pytest.param(
                "creating_pr", {"pr_url": "https://github.com/example/repo/pull/2"},
                "creating_pr", {"pr_url": "https://github.com/example/repo/pull/3"},
                id="all_ready_none_done_returns_waiting",
            ),
        ],
    )
    def test_is_task_eligible_two_dependencies_short_of_done_returns_waiting(
        self, tmp_path, monkeypatch, dep2_state, dep2_extra, dep3_state, dep3_extra
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state=dep2_state, **dep2_extra).save(
            compute_context_path("ADR-2", repo_slug)
        )
        PipelineContext(work_item_id="ADR-3", state=dep3_state, **dep3_extra).save(
            compute_context_path("ADR-3", repo_slug)
        )

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == "waiting"


# ---------------------------------------------------------------------------
# is_task_eligible — a failed dependency short-circuits to blocked, regardless of any
# other dependency's status
# ---------------------------------------------------------------------------

class TestIsTaskEligibleFailedDependency:
    def test_is_task_eligible_one_failed_amid_one_done_returns_blocked(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state="failed").save(compute_context_path("ADR-2", repo_slug))
        PipelineContext(work_item_id="ADR-3", state="done").save(compute_context_path("ADR-3", repo_slug))

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == "blocked"


# ---------------------------------------------------------------------------
# main() CLI wrapper — one narrow integration test for the primary happy-path scenario.
# `base_branch` stays an unconditional `null` in the JSON shape; no current skill invokes this
# CLI form via `Bash` (callers use the Python API directly).
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_single_done_dependency_prints_eligible_with_null_base_branch(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        dep_path = compute_context_path("ADR-2", get_repo_slug())
        PipelineContext(work_item_id="ADR-2", state="done").save(dep_path)

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "task_readiness.py"), "ADR-1", "ADR-2"],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"status": "eligible", "base_branch": None}
