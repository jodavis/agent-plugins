"""Tests for task_readiness.py — dependency_status() (a dependency task-work-item's own
context file translated into a coarse status) and is_task_eligible() (whether a task is
eligible to start given its declared dependencies' statuses).

Covers:
- dependency_status: no context file, terminal states (done/failed), pr_url-implies-ready,
  and the in_progress fallback
- is_task_eligible: empty dependency list, single-dependency ready/not-ready, all-done,
  all-but-one-done (ready branch substitution and waiting), 2+ not-done, and failed dependency
  short-circuiting to blocked
- main() CLI wrapper: one narrow integration test covering the primary happy-path — a single
  ready dependency prints its branch as JSON on stdout, exit 0 — the wiring `ensure-working-branch`
  relies on to call this script via `Bash`
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
            work_item_id="ADR-1", state="creating-pr", pr_url="https://github.com/example/repo/pull/1"
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
# is_task_eligible — empty dependency list
# ---------------------------------------------------------------------------

class TestIsTaskEligibleEmptyDependencies:
    def test_is_task_eligible_empty_dependency_ids_returns_eligible_with_no_base_branch(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import is_task_eligible

        # Act
        result = is_task_eligible("ADR-1", [])

        # Assert
        assert result == ("eligible", None)


# ---------------------------------------------------------------------------
# is_task_eligible — single dependency, ready vs. not yet ready
# ---------------------------------------------------------------------------

class TestIsTaskEligibleSingleDependency:
    @pytest.mark.parametrize(
        "dep_context_kwargs, expected_result",
        [
            pytest.param(
                dict(
                    state="creating-pr",
                    pr_url="https://github.com/example/repo/pull/2",
                    extra_frontmatter={"working_branch": "dev/claude/ADR-2"},
                ),
                ("eligible", "dev/claude/ADR-2"),
                id="ready_returns_eligible_with_its_working_branch",
            ),
            pytest.param(
                dict(state="researching"),
                ("waiting", None),
                id="in_progress_returns_waiting_with_no_base_branch",
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
    def test_is_task_eligible_single_dependency_not_started_returns_waiting_with_no_base_branch(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from task_readiness import is_task_eligible

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2"])

        # Assert
        assert result == ("waiting", None)


# ---------------------------------------------------------------------------
# is_task_eligible — two dependencies, all but one done and the remaining one ready
# ---------------------------------------------------------------------------

class TestIsTaskEligibleAllButOneDone:
    def test_is_task_eligible_all_but_one_done_and_remaining_ready_returns_eligible_with_its_working_branch(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state="done").save(compute_context_path("ADR-2", repo_slug))
        PipelineContext(
            work_item_id="ADR-3",
            state="creating-pr",
            pr_url="https://github.com/example/repo/pull/3",
            extra_frontmatter={"working_branch": "dev/claude/ADR-3"},
        ).save(compute_context_path("ADR-3", repo_slug))

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == ("eligible", "dev/claude/ADR-3")


# ---------------------------------------------------------------------------
# is_task_eligible — two or more dependencies short of done, none of them ready
# ---------------------------------------------------------------------------

class TestIsTaskEligibleTwoOrMoreNotDone:
    def test_is_task_eligible_two_dependencies_neither_done_nor_ready_returns_waiting(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state="researching").save(compute_context_path("ADR-2", repo_slug))
        PipelineContext(work_item_id="ADR-3", state="planning").save(compute_context_path("ADR-3", repo_slug))

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == ("waiting", None)


# ---------------------------------------------------------------------------
# is_task_eligible — two dependencies: all done, vs. one failed amid the other
# ---------------------------------------------------------------------------

class TestIsTaskEligibleTwoDependencies:
    @pytest.mark.parametrize(
        "dep2_state, expected_result",
        [
            pytest.param("done", ("eligible", None), id="all_done_returns_eligible_with_no_base_branch"),
            pytest.param("failed", ("blocked", None), id="one_failed_amid_one_done_returns_blocked"),
        ],
    )
    def test_is_task_eligible_two_dependencies_returns_expected_result(
        self, tmp_path, monkeypatch, dep2_state, expected_result
    ):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext
        from task_readiness import is_task_eligible

        repo_slug = get_repo_slug()
        PipelineContext(work_item_id="ADR-2", state=dep2_state).save(compute_context_path("ADR-2", repo_slug))
        PipelineContext(work_item_id="ADR-3", state="done").save(compute_context_path("ADR-3", repo_slug))

        # Act
        result = is_task_eligible("ADR-1", ["ADR-2", "ADR-3"])

        # Assert
        assert result == expected_result


# ---------------------------------------------------------------------------
# main() CLI wrapper — the only wiring `ensure-working-branch`'s prose SKILL.md can invoke via
# `Bash`; one narrow integration test for the primary happy-path scenario
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_single_ready_dependency_prints_eligible_with_its_branch(self, tmp_path, monkeypatch):
        # Arrange
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        dep_path = compute_context_path("ADR-2", get_repo_slug())
        PipelineContext(
            work_item_id="ADR-2",
            state="creating-pr",
            pr_url="https://github.com/example/repo/pull/2",
            extra_frontmatter={"working_branch": "dev/claude/ADR-2"},
        ).save(dep_path)

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "task_readiness.py"), "ADR-1", "ADR-2"],
            capture_output=True, text=True, timeout=15,
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"status": "eligible", "base_branch": "dev/claude/ADR-2"}

