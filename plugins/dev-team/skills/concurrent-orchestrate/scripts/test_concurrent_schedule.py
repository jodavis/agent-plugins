"""Tests for concurrent_schedule.py — compute_next_batch() computes the "up to" target's
dependency closure (or takes an explicit list as-is, with no closure expansion), validates an
explicit list's dependencies upfront, tracks each target task's cached status via the Task
readiness checker, enforces a repo-wide concurrency cap across every
`concurrent-<target-slug>.json` file, and never spawns anything itself.

Covers:
- TargetSpec / target_slug: "up to" vs. explicit-list slug derivation
- compute_next_batch: closure computation ("up to"), no expansion (explicit list), persistence
  of the target's own data file
- Explicit-list upfront validation: rejects a dependency neither in the list nor done; accepts
  one that is
- compute_next_batch: "waiting" with newly eligible spawn, "complete" once all done, "blocked"
  once every spawned task is terminal but a not-yet-started task has a failed ancestor, and
  the not-yet-blocked case where an active (non-terminal) spawn still exists
- Repo-wide concurrency cap: enforced across multiple target data files, not just its own
- _max_parallel_tasks: default (3) and project-configured override
- compute_next_batch: "running" includes a task_snapshot() entry for each non-terminal
  already-spawned task, and excludes one once it reaches a terminal state
- main() CLI wrapper: one narrow integration test for the primary happy path
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent


def _write_spec(tmp_path: Path, edges: dict[str, list[str]]) -> Path:
    """Write a fake `_spec_Test.md` file into `tmp_path` with one `### [KEY: Title](url) 🤖`
    heading per key in `edges`, each followed by a `**Depends on:**` line built from its
    dependency list (or `— none —`)."""
    lines = []
    for key, deps in edges.items():
        lines.append(f"### [{key}: Title](https://example.atlassian.net/browse/{key}) 🤖")
        lines.append("")
        if deps:
            lines.append(f"**Depends on:** {', '.join(deps)}")
        else:
            lines.append("**Depends on:** — none —")
        lines.append("")
    spec_path = tmp_path / "_spec_Test.md"
    spec_path.write_text("\n".join(lines), encoding="utf-8")
    return spec_path


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """Common env seams every test needs: an isolated state dir and a fixed repo slug."""
    monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
    return tmp_path


def _set_repo_root(tmp_path, monkeypatch):
    import dev_team
    monkeypatch.setattr(dev_team, "REPO_ROOT", tmp_path)


def _save_context(work_item_id: str, **kwargs) -> None:
    from dev_team import compute_context_path
    from get_context_path import get_repo_slug
    from pipeline_context import PipelineContext

    path = compute_context_path(work_item_id, get_repo_slug())
    PipelineContext(work_item_id=work_item_id, **kwargs).save(path)


# ---------------------------------------------------------------------------
# target_slug
# ---------------------------------------------------------------------------

class TestTargetSlug:
    def test_target_slug_up_to_mode_uses_up_to_prefixed_key(self):
        from concurrent_schedule import TargetSpec, target_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-310",))

        assert target_slug(target) == "up-to-ADR-310"

    def test_target_slug_list_mode_uses_sorted_joined_keys(self):
        from concurrent_schedule import TargetSpec, target_slug

        target = TargetSpec(mode="list", tasks=("ADR-312", "ADR-310", "ADR-311"))

        assert target_slug(target) == "ADR-310-ADR-311-ADR-312"


# ---------------------------------------------------------------------------
# compute_next_batch — "up to" closure computation
# ---------------------------------------------------------------------------

class TestComputeNextBatchUpToClosure:
    def test_compute_next_batch_up_to_expands_transitive_closure_and_spawns_root_dependency(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": ["ADR-3"],
            "ADR-3": [],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-3", "base_branch": None}]
        assert result["blocked_tasks"] == []
        data = json.loads(_data_file_path(get_repo_slug(), target).read_text(encoding="utf-8"))
        assert data["tasks"] == ["ADR-1", "ADR-2", "ADR-3"]
        assert data["mode"] == "up_to"


# ---------------------------------------------------------------------------
# compute_next_batch — explicit list, no closure expansion
# ---------------------------------------------------------------------------

class TestComputeNextBatchListNoExpansion:
    def test_compute_next_batch_list_mode_does_not_expand_beyond_given_tasks(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": ["ADR-3"],
            "ADR-3": [],
        })
        _save_context("ADR-3", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="list", tasks=("ADR-1", "ADR-2"))

        # Act
        compute_next_batch(target)

        # Assert
        data = json.loads(_data_file_path(get_repo_slug(), target).read_text(encoding="utf-8"))
        assert data["tasks"] == ["ADR-1", "ADR-2"]
        assert data["mode"] == "list"


# ---------------------------------------------------------------------------
# Explicit list upfront validation
# ---------------------------------------------------------------------------

class TestExplicitListValidation:
    def test_compute_next_batch_list_dependency_outside_list_and_not_done_raises(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
        })
        from concurrent_schedule import ConcurrentScheduleError, TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1",))

        # Act & Assert
        with pytest.raises(ConcurrentScheduleError, match="ADR-1.*ADR-2"):
            compute_next_batch(target)

    def test_compute_next_batch_list_dependency_outside_list_but_already_done_is_accepted(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
        })
        _save_context("ADR-2", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert — no exception, and normal scheduling proceeds
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-1", "base_branch": None}]


# ---------------------------------------------------------------------------
# compute_next_batch — "complete"
# ---------------------------------------------------------------------------

class TestComputeNextBatchComplete:
    def test_compute_next_batch_all_tasks_done_returns_complete_with_empty_spawn(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        _save_context("ADR-1", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result == {"status": "complete", "spawn": [], "blocked_tasks": [], "running": []}


# ---------------------------------------------------------------------------
# compute_next_batch — "blocked"
# ---------------------------------------------------------------------------

class TestComputeNextBatchBlocked:
    def test_compute_next_batch_failed_dependency_with_no_active_spawns_returns_blocked(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
        })
        _save_context("ADR-2", state="failed")
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result == {"status": "blocked", "spawn": [], "blocked_tasks": ["ADR-1"], "running": []}

    def test_compute_next_batch_failed_dependency_with_active_spawn_still_waiting(
        self, tmp_path, monkeypatch
    ):
        # Arrange — ADR-2 and ADR-4 both have no dependencies, so the first call spawns both.
        # ADR-2 then fails, but ADR-4 (also spawned) stays in progress (non-terminal). Since not
        # every currently-spawned task has reached a terminal state yet, the scheduler must not
        # report "blocked" for ADR-1 yet, even though ADR-1 can already never become eligible.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
            "ADR-4": [],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1", "ADR-2", "ADR-4"))
        first = compute_next_batch(target)
        assert {entry["task_id"] for entry in first["spawn"]} == {"ADR-2", "ADR-4"}

        _save_context("ADR-2", state="failed")
        _save_context("ADR-4", state="researching")  # spawned, still in progress (non-terminal)

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == []

    def test_compute_next_batch_blocked_once_active_spawn_reaches_terminal(
        self, tmp_path, monkeypatch
    ):
        # Arrange — same setup as above, but ADR-4 (the one active spawn) has now reached its
        # own terminal state, so the scheduler can finally report "blocked" for ADR-1.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
            "ADR-4": [],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1", "ADR-2", "ADR-4"))
        compute_next_batch(target)

        _save_context("ADR-2", state="failed")
        _save_context("ADR-4", state="done")

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result == {"status": "blocked", "spawn": [], "blocked_tasks": ["ADR-1"], "running": []}


# ---------------------------------------------------------------------------
# compute_next_batch — "running"
# ---------------------------------------------------------------------------

class TestComputeNextBatchRunning:
    def test_compute_next_batch_running_includes_snapshot_for_non_terminal_spawned_task(
        self, tmp_path, monkeypatch
    ):
        # Arrange — first call spawns ADR-1 (no dependencies); once its context file reflects a
        # non-terminal, in-progress state with a worktree_path, a second call must report it in
        # "running" with its snapshot fields populated.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        from concurrent_schedule import TargetSpec, compute_next_batch
        from task_readiness import task_snapshot

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        compute_next_batch(target)
        _save_context(
            "ADR-1", state="researching",
            extra_frontmatter={"worktree_path": "/tmp/worktrees/ADR-1"},
        )

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["running"] == [{"task_id": "ADR-1", **task_snapshot("ADR-1")}]

    def test_compute_next_batch_running_excludes_task_once_it_reaches_terminal_state(
        self, tmp_path, monkeypatch
    ):
        # Arrange — ADR-2 has no dependencies, so the first call spawns it, leaving ADR-1
        # (which depends on ADR-2) not yet started. Once ADR-2's context file reflects "done"
        # (terminal), the second call must both newly spawn ADR-1 (now eligible) and exclude
        # ADR-2 from "running", since it's no longer non-terminal.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": ["ADR-2"],
            "ADR-2": [],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        first = compute_next_batch(target)
        assert first["spawn"] == [{"task_id": "ADR-2", "base_branch": None}]
        _save_context("ADR-2", state="done")

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["running"] == []

    def test_compute_next_batch_running_reads_each_spawned_tasks_context_file_only_once(
        self, tmp_path, monkeypatch
    ):
        # Arrange — ADR-1 is spawned and non-terminal, so it lands in both `statuses` (used to
        # decide it isn't yet "complete"/"blocked") and `running`. Those two must share a single
        # context-file read per task, not one read to build `statuses` and a second, independent
        # one to build the `running` snapshot — the second read would double I/O on every poll
        # cycle and could observe a different (later) state than the one `statuses` already
        # decided on. (A third, separate read of the same file happens via
        # `_repo_wide_active_spawn_count`'s repo-wide concurrency-cap scan, which reads every
        # target's own spawned set independently of this call's `statuses`/`running` and is out
        # of scope here — so 2 reads, not 1, is the fixed-and-correct count.)
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        from concurrent_schedule import TargetSpec, compute_next_batch
        import pipeline_context

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        compute_next_batch(target)
        _save_context(
            "ADR-1", state="researching",
            extra_frontmatter={"worktree_path": "/tmp/worktrees/ADR-1"},
        )

        load_call_paths: list[str] = []
        real_load = pipeline_context.PipelineContext.load.__func__

        def _counting_load(cls, path):
            load_call_paths.append(str(path))
            return real_load(cls, path)

        monkeypatch.setattr(
            pipeline_context.PipelineContext, "load", classmethod(_counting_load)
        )

        # Act
        compute_next_batch(target)

        # Assert — two context-file reads for ADR-1 while computing this batch: one shared by
        # `statuses`/`running`, one from the separate repo-wide concurrency-cap scan.
        assert load_call_paths.count(load_call_paths[0]) == 2


# ---------------------------------------------------------------------------
# poll_until_actionable — blocking wait for something actionable
# ---------------------------------------------------------------------------

class TestPollUntilActionable:
    def test_poll_until_actionable_returns_immediately_when_first_poll_has_spawn(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        from concurrent_schedule import TargetSpec, poll_until_actionable

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        sleeps: list[float] = []

        # Act
        result = poll_until_actionable(target, sleep=sleeps.append)

        # Assert — spawn is non-empty on the very first poll, so no sleep is ever needed
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-1", "base_branch": None}]
        assert sleeps == []

    def test_poll_until_actionable_returns_immediately_on_complete_without_sleeping(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        _save_context("ADR-1", state="done")
        from concurrent_schedule import TargetSpec, poll_until_actionable

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        sleeps: list[float] = []

        # Act
        result = poll_until_actionable(target, sleep=sleeps.append)

        # Assert
        assert result["status"] == "complete"
        assert sleeps == []

    def test_poll_until_actionable_sleeps_and_repolls_while_idle_then_returns_new_spawn(
        self, tmp_path, monkeypatch
    ):
        # Arrange — ADR-1 depends on ADR-2, which isn't done yet, so the first poll spawns
        # ADR-2 and nothing is left to spawn for ADR-1 until ADR-2 finishes. Once ADR-2 is
        # marked "done" partway through polling, the next poll should surface ADR-1 as newly
        # eligible instead of exhausting all cycles.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": ["ADR-2"], "ADR-2": []})
        _save_context("ADR-2", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch, poll_until_actionable

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        # First real poll (outside the function, to seed "spawned") — simulate ADR-1 already
        # spawned so the very first internal poll comes back idle ("waiting", empty spawn).
        first = compute_next_batch(target)
        assert first["spawn"] == [{"task_id": "ADR-1", "base_branch": None}]
        _save_context("ADR-1", state="researching")  # active, non-terminal — still "waiting"

        sleeps: list[float] = []
        call_count = 0
        real_compute_next_batch = compute_next_batch

        def _fake_compute(t):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                _save_context("ADR-1", state="done")
            return real_compute_next_batch(t)

        monkeypatch.setattr("concurrent_schedule.compute_next_batch", _fake_compute)

        # Act
        result = poll_until_actionable(
            target, poll_interval_seconds=5, max_poll_cycles=10, sleep=sleeps.append,
        )

        # Assert — one idle poll, one sleep, then "complete" on the second poll
        assert result["status"] == "complete"
        assert sleeps == [5]
        assert call_count == 2

    def test_poll_until_actionable_gives_up_after_max_poll_cycles_still_idle(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a single task with an unmet dependency stays "waiting" with an empty spawn
        # forever (nothing newly eligible), so the poll loop must give up after exhausting its
        # configured cycle budget rather than blocking indefinitely.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": ["ADR-2"], "ADR-2": []})
        _save_context("ADR-2", state="researching")  # never reaches "done"
        from concurrent_schedule import TargetSpec, poll_until_actionable

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        sleeps: list[float] = []

        # Act
        result = poll_until_actionable(
            target, poll_interval_seconds=30, max_poll_cycles=3, sleep=sleeps.append,
        )

        # Assert — initial poll + 3 more, each preceded by one 30s sleep
        assert result["status"] == "waiting"
        assert result["spawn"] == []
        assert sleeps == [30, 30, 30]


# ---------------------------------------------------------------------------
# Repo-wide concurrency cap enforcement
# ---------------------------------------------------------------------------

class TestConcurrencyCap:
    def test_compute_next_batch_caps_spawn_to_available_slots(self, tmp_path, monkeypatch):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": [], "ADR-2": [], "ADR-3": []})
        import concurrent_schedule
        monkeypatch.setattr(concurrent_schedule, "_max_parallel_tasks", lambda repo_root: 2)
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1", "ADR-2", "ADR-3"))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert len(result["spawn"]) == 2

    def test_compute_next_batch_counts_active_spawns_from_other_target_files_repo_wide(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a different target's data file already has one active (non-terminal) spawn
        # tracked; this target's own cap check must count it too.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-5": [], "ADR-6": []})
        import concurrent_schedule
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        monkeypatch.setattr(concurrent_schedule, "_max_parallel_tasks", lambda repo_root: 1)

        other_target = TargetSpec(mode="up_to", tasks=("ADR-99",))
        other_path = _data_file_path(get_repo_slug(), other_target)
        other_path.parent.mkdir(parents=True, exist_ok=True)
        other_path.write_text(
            json.dumps({"mode": "up_to", "tasks": ["ADR-99"], "spawned": ["ADR-99"]}),
            encoding="utf-8",
        )
        _save_context("ADR-99", state="researching")  # active, non-terminal

        target = TargetSpec(mode="list", tasks=("ADR-5", "ADR-6"))

        # Act
        result = compute_next_batch(target)

        # Assert — cap of 1 is already consumed by ADR-99, so nothing new spawns
        assert result["status"] == "waiting"
        assert result["spawn"] == []

    def test_compute_next_batch_does_not_count_terminal_spawns_from_other_target_files(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a different target's data file has a spawn that already reached "done", so
        # it must not consume this target's cap slot.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-7": []})
        import concurrent_schedule
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        monkeypatch.setattr(concurrent_schedule, "_max_parallel_tasks", lambda repo_root: 1)

        other_target = TargetSpec(mode="up_to", tasks=("ADR-98",))
        other_path = _data_file_path(get_repo_slug(), other_target)
        other_path.parent.mkdir(parents=True, exist_ok=True)
        other_path.write_text(
            json.dumps({"mode": "up_to", "tasks": ["ADR-98"], "spawned": ["ADR-98"]}),
            encoding="utf-8",
        )
        _save_context("ADR-98", state="done")

        target = TargetSpec(mode="list", tasks=("ADR-7",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["spawn"] == [{"task_id": "ADR-7", "base_branch": None}]


# ---------------------------------------------------------------------------
# _max_parallel_tasks
# ---------------------------------------------------------------------------

class TestMaxParallelTasks:
    def test_max_parallel_tasks_defaults_to_three(self, tmp_path):
        from concurrent_schedule import _max_parallel_tasks

        assert _max_parallel_tasks(tmp_path) == 3

    def test_max_parallel_tasks_uses_project_override(self, tmp_path):
        config_dir = tmp_path / ".dev-team"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text(
            "concurrency:\n  max-parallel-tasks: 7\n", encoding="utf-8"
        )
        from concurrent_schedule import _max_parallel_tasks

        assert _max_parallel_tasks(tmp_path) == 7


# ---------------------------------------------------------------------------
# main() CLI wrapper — one narrow integration test for the primary happy path
# ---------------------------------------------------------------------------

class TestMainCliWrapper:
    def test_main_up_to_single_task_no_dependencies_prints_waiting_with_spawn(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a `.git` marker so dev_team.py's own repo-root discovery resolves to
        # tmp_path (where the fake spec lives), the same way it would in a real checkout.
        (tmp_path / ".git").mkdir()
        _write_spec(tmp_path, {"ADR-1": []})
        import os
        full_env = {**os.environ, "DEV_TEAM_STATE_DIR": str(tmp_path),
                     "GIT_REMOTE_URL_OVERRIDE": "https://github.com/example/repo.git"}

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "concurrent_schedule.py"), "--up-to", "ADR-1"],
            capture_output=True, text=True, timeout=15, env=full_env, cwd=str(tmp_path),
        )

        # Assert
        assert result.returncode == 0
        assert json.loads(result.stdout) == {
            "status": "waiting",
            "spawn": [{"task_id": "ADR-1", "base_branch": None}],
            "blocked_tasks": [],
            "running": [],
        }

    def test_main_list_dependency_outside_list_and_not_done_prints_error_and_exits_nonzero(
        self, tmp_path
    ):
        # Arrange
        (tmp_path / ".git").mkdir()
        _write_spec(tmp_path, {"ADR-1": ["ADR-2"], "ADR-2": []})
        import os
        full_env = {**os.environ, "DEV_TEAM_STATE_DIR": str(tmp_path),
                     "GIT_REMOTE_URL_OVERRIDE": "https://github.com/example/repo.git"}

        # Act
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "concurrent_schedule.py"), "--list", "ADR-1"],
            capture_output=True, text=True, timeout=15, env=full_env, cwd=str(tmp_path),
        )

        # Assert
        assert result.returncode == 1
        assert result.stdout == ""
        assert "Error:" in result.stderr


# ---------------------------------------------------------------------------
# main() CLI wrapper — exception-handling coverage beyond the documented
# (TaskDependencyError, ConcurrentScheduleError, OSError, RuntimeError) tuple
# ---------------------------------------------------------------------------

class TestMainUnhandledFailureModes:
    def test_main_corrupted_data_file_prints_clean_error_and_exits_nonzero(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange — a target's own data file exists but is not valid JSON, simulating
        # on-disk corruption of `concurrent-<target-slug>.json`.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        import concurrent_schedule
        from concurrent_schedule import TargetSpec, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        data_path = _data_file_path(get_repo_slug(), target)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["concurrent_schedule.py", "--up-to", "ADR-1"])

        # Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            concurrent_schedule.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error:" in captured.err

    def test_main_merge_config_subprocess_timeout_prints_clean_error_and_exits_nonzero(
        self, tmp_path, monkeypatch, capsys
    ):
        # Arrange — `_max_parallel_tasks`'s call to `merge_config.py` times out.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        import concurrent_schedule
        from concurrent_schedule import TargetSpec

        def _raise_timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="merge_config.py", timeout=30)

        monkeypatch.setattr(concurrent_schedule.subprocess, "run", _raise_timeout)
        monkeypatch.setattr(sys, "argv", ["concurrent_schedule.py", "--up-to", "ADR-1"])

        # Act & Assert
        with pytest.raises(SystemExit) as exc_info:
            concurrent_schedule.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Error:" in captured.err
