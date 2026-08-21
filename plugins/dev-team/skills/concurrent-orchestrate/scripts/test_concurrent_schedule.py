"""Tests for concurrent_schedule.py — compute_next_batch() computes the "up to" target's
inclusive document-order task set (or takes an explicit list as-is, with no expansion),
validates an explicit list's dependencies upfront, tracks each target task's cached status via
the Task readiness checker, gates on a live "is the epic's feature branch bootstrapped yet?"
check before computing any batch, and enforces a repo-wide concurrency cap across every
`concurrent-<target-slug>.json` file — never spawning anything itself.

Covers:
- TargetSpec / target_slug: "up to" vs. explicit-list slug derivation
- compute_next_batch: "up to" inclusive document-order task set (ADR-374 — a deliberate
  behavior change from the old dependency-closure-only form), no expansion (explicit list),
  persistence of the target's own data file
- Explicit-list upfront validation: rejects a dependency neither in the list nor done; accepts
  one that is
- compute_next_batch: "waiting" with newly eligible spawn, "complete" once all done, "blocked"
  once every spawned task is terminal but a not-yet-started task has a failed ancestor, and
  the not-yet-blocked case where an active (non-terminal) spawn still exists
- compute_next_batch: "bootstrap_needed" — gated on a live `git branch -r` check, never on the
  target's own data-file presence, so a retry after the branch is created proceeds normally and
  a different, already-bootstrapped target never round-trips through it at all
- Repo-wide concurrency cap: enforced across multiple target data files, not just its own
- _max_parallel_tasks: default (3) and project-configured override
- compute_next_batch: "running" includes a task_snapshot() entry for each non-terminal
  already-spawned task, and excludes one once it reaches a terminal state
- main() CLI wrapper: one narrow integration test for the primary happy path, exercising the
  live bootstrap check for real (via a minimal throwaway git repo) since it can't be
  monkeypatched across a subprocess boundary
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent

_DEFAULT_EPIC_ID = "ADR-369"

# Captured at module-import time, before the autouse `_env` fixture below monkeypatches
# `concurrent_schedule._feature_branch_exists` for every test — so `TestFeatureBranchExists`
# can exercise the real implementation directly instead of picking up its own stub.
import concurrent_schedule as _concurrent_schedule_module

_real_feature_branch_exists = _concurrent_schedule_module._feature_branch_exists


def _write_spec(tmp_path: Path, edges: dict[str, list[str]], epic_id: str = _DEFAULT_EPIC_ID) -> Path:
    """Write a fake `_spec_Test.md` file into `tmp_path`: a `> **Epic:** [<key>](url)` header
    line (the only local, MCP-free source `_parse_epic_id` has to read from) followed by one
    `### [KEY: Title](url) 🤖` heading per key in `edges`, each followed by a `**Depends on:**`
    line built from its dependency list (or `— none —`)."""
    lines = [
        f"> **Epic:** [{epic_id}](https://example.atlassian.net/browse/{epic_id})",
        "",
    ]
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


def _stub_feature_branch_exists(monkeypatch, *, exists: bool) -> None:
    """Stub `concurrent_schedule._feature_branch_exists` so tests don't depend on a real git
    remote existing under `tmp_path` — mirroring how `_max_parallel_tasks` is monkeypatched
    wholesale elsewhere in this file rather than stubbing the subprocess call underneath it.
    Defaults to `exists=True` (already bootstrapped) via the autouse `_env` fixture below, so
    every test not specifically exercising bootstrap detection behaves as it did before this
    check existed."""
    import concurrent_schedule
    monkeypatch.setattr(concurrent_schedule, "_feature_branch_exists", lambda epic_id, repo_root: exists)


def _init_git_repo_with_remote_branch(tmp_path: Path, branch_name: str) -> None:
    """Set up a minimal local git repo whose `git branch -r` output includes a remote-tracking
    ref for `branch_name`, without needing a real remote. Used only by the CLI-level (subprocess)
    test that exercises the live bootstrap check for real, since `_feature_branch_exists` can't
    be monkeypatched across a subprocess boundary — it also gives `dev_team.py`'s own repo-root
    discovery a genuine `.git` to resolve to `tmp_path`."""
    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=tmp_path, check=True, capture_output=True, text=True, timeout=15)

    _run("git", "init", "-q")
    _run("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "--allow-empty", "-q", "-m", "init")
    sha = _run("git", "rev-parse", "HEAD").stdout.strip()
    _run("git", "update-ref", f"refs/remotes/origin/{branch_name}", sha)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    """Common env seams every test needs: an isolated state dir, a fixed repo slug, and the
    epic feature branch already treated as bootstrapped by default."""
    monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
    _stub_feature_branch_exists(monkeypatch, exists=True)
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
# compute_next_batch — "up to" inclusive document-order task set (ADR-374)
# ---------------------------------------------------------------------------

class TestComputeNextBatchUpToDocumentOrder:
    def test_compute_next_batch_up_to_includes_every_task_through_target_in_document_order_and_spawns_root_dependency(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a linear chain, where document order and dependency closure coincide
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-3": [],
            "ADR-2": ["ADR-3"],
            "ADR-1": ["ADR-2"],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-3"}]
        assert result["blocked_tasks"] == []
        data = json.loads(_data_file_path(get_repo_slug(), target).read_text(encoding="utf-8"))
        assert data["tasks"] == ["ADR-3", "ADR-2", "ADR-1"]
        assert data["mode"] == "up_to"

    def test_compute_next_batch_up_to_includes_unrelated_earlier_task_not_in_targets_dependency_closure(
        self, tmp_path, monkeypatch
    ):
        # Arrange — ADR-374's deliberate behavior change from ADR-296: "up to ADR-4" now means
        # every task from the start of document order through ADR-4 inclusive, not just ADR-4's
        # own transitive dependency closure. ADR-2 and ADR-3 are unrelated to ADR-4 (ADR-4
        # depends only on ADR-1) but are still earlier in document order, so both must still be
        # included and spawned alongside ADR-1. The concurrency cap is stubbed generously high
        # so this test's assertions reflect eligibility, not an incidental cap collision.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {
            "ADR-1": [],
            "ADR-2": [],
            "ADR-3": [],
            "ADR-4": ["ADR-1"],
        })
        import concurrent_schedule
        monkeypatch.setattr(concurrent_schedule, "_max_parallel_tasks", lambda repo_root: 10)
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-4",))

        # Act
        result = compute_next_batch(target)

        # Assert
        data = json.loads(_data_file_path(get_repo_slug(), target).read_text(encoding="utf-8"))
        assert data["tasks"] == ["ADR-1", "ADR-2", "ADR-3", "ADR-4"]
        assert {entry["task_id"] for entry in result["spawn"]} == {"ADR-1", "ADR-2", "ADR-3"}


# ---------------------------------------------------------------------------
# compute_next_batch — "up to" target not a valid task heading
# ---------------------------------------------------------------------------

class TestComputeNextBatchUpToTargetNotInDocumentOrder:
    def test_compute_next_batch_up_to_target_not_a_task_heading_raises_concurrent_schedule_error(
        self, tmp_path, monkeypatch
    ):
        # Arrange — "up to ADR-369" resolves to this spec file via find_spec_file's plain
        # substring search (ADR-369 appears in the Epic header line), but ADR-369 is not itself
        # a "### [KEY: Title]" task heading, so it never appears in validate_stack_order's
        # document order. order.index() must not propagate a raw ValueError here — it must
        # raise a ConcurrentScheduleError, the same clean "Error: ..." family every other bad
        # "up to"/explicit-list input in this module already raises.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": [], "ADR-2": ["ADR-1"]}, epic_id="ADR-369")
        from concurrent_schedule import ConcurrentScheduleError, TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-369",))

        # Act & Assert
        with pytest.raises(ConcurrentScheduleError, match="ADR-369"):
            compute_next_batch(target)


# ---------------------------------------------------------------------------
# compute_next_batch — explicit list, no expansion
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
            "ADR-2": [],
            "ADR-1": ["ADR-2"],
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
            "ADR-2": [],
            "ADR-1": ["ADR-2"],
        })
        _save_context("ADR-2", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="list", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert — no exception, and normal scheduling proceeds
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-1"}]


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
            "ADR-2": [],
            "ADR-1": ["ADR-2"],
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
            "ADR-2": [],
            "ADR-1": ["ADR-2"],
        })
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        first = compute_next_batch(target)
        assert first["spawn"] == [{"task_id": "ADR-2"}]
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
# compute_next_batch — "bootstrap_needed": a live check, never a data-file check
# ---------------------------------------------------------------------------

class TestBootstrapNeeded:
    def test_compute_next_batch_feature_branch_absent_returns_bootstrap_needed_before_computing_batch(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        _stub_feature_branch_exists(monkeypatch, exists=False)
        from concurrent_schedule import TargetSpec, compute_next_batch, _data_file_path
        from get_context_path import get_repo_slug

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result == {
            "status": "bootstrap_needed", "epic_id": _DEFAULT_EPIC_ID,
            "spawn": [], "blocked_tasks": [], "running": [],
        }
        # The data file is still persisted, independent of the bootstrap signal.
        data = json.loads(_data_file_path(get_repo_slug(), target).read_text(encoding="utf-8"))
        assert data["tasks"] == ["ADR-1"]

    def test_compute_next_batch_same_target_retry_after_branch_created_proceeds_to_batch(
        self, tmp_path, monkeypatch
    ):
        # Arrange — the same target's second call, once `ensure-feature-branch` has created the
        # branch in response to the first call's `bootstrap_needed`, must find the branch now
        # exists and proceed to compute a batch — never report `bootstrap_needed` a second time.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-1": []})
        _stub_feature_branch_exists(monkeypatch, exists=False)
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        first = compute_next_batch(target)
        assert first["status"] == "bootstrap_needed"

        _stub_feature_branch_exists(monkeypatch, exists=True)

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-1"}]

    def test_compute_next_batch_different_target_first_call_already_bootstrapped_proceeds_directly(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a second, different target's first call against an already-bootstrapped
        # epic must find the branch already exists on its very first check, and proceed
        # directly to computing a batch — no `bootstrap_needed` round-trip at all. A single-task
        # target keeps this test focused on the bootstrap round-trip itself, not on the
        # separately-covered inclusive "up to" ordering semantics.
        _set_repo_root(tmp_path, monkeypatch)
        _write_spec(tmp_path, {"ADR-5": []})
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-5",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-5"}]

    def test_compute_next_batch_no_epic_header_line_skips_bootstrap_gating(
        self, tmp_path, monkeypatch
    ):
        # Arrange — a spec with no `> **Epic:**` header line at all (predates this convention,
        # or malformed): there is nothing to gate bootstrap on, so scheduling must proceed
        # normally rather than erroring or looping.
        _set_repo_root(tmp_path, monkeypatch)
        spec_path = tmp_path / "_spec_Test.md"
        spec_path.write_text(
            "### [ADR-1: Title](https://example.atlassian.net/browse/ADR-1) 🤖\n\n"
            "**Depends on:** — none —\n",
            encoding="utf-8",
        )
        _stub_feature_branch_exists(monkeypatch, exists=False)
        from concurrent_schedule import TargetSpec, compute_next_batch

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))

        # Act
        result = compute_next_batch(target)

        # Assert
        assert result["status"] == "waiting"
        assert result["spawn"] == [{"task_id": "ADR-1"}]


# ---------------------------------------------------------------------------
# _feature_branch_prefix — derived from git-repo.working-branches.task, not a separate
# "feature" template
# ---------------------------------------------------------------------------

class TestFeatureBranchPrefix:
    def test_defaults_to_dev_claude(self, tmp_path):
        from concurrent_schedule import _feature_branch_prefix

        assert _feature_branch_prefix(tmp_path) == "dev/claude/"

    def test_uses_project_override(self, tmp_path):
        config_dir = tmp_path / ".dev-team"
        config_dir.mkdir()
        (config_dir / "config.yaml").write_text(
            "git-repo:\n"
            "  user-alias: bot\n"
            "  working-branches:\n"
            "    task: work/<user-alias>/<task-work-item-id>-<slug>\n",
            encoding="utf-8",
        )
        from concurrent_schedule import _feature_branch_prefix

        assert _feature_branch_prefix(tmp_path) == "work/bot/"


# ---------------------------------------------------------------------------
# _feature_branch_exists — live `git branch -r` check
# ---------------------------------------------------------------------------

class TestFeatureBranchExists:
    def test_feature_branch_exists_exact_match_returns_true(self, tmp_path):
        # Arrange
        _init_git_repo_with_remote_branch(tmp_path, "dev/claude/ADR-369-spec")

        # Act & Assert
        assert _real_feature_branch_exists("ADR-369", tmp_path) is True

    def test_feature_branch_exists_suffixed_match_returns_true(self, tmp_path):
        # Arrange — a branch like `dev/claude/ADR-369-spec-stack` must still match: the
        # anchoring only needs to rule out a *different*, longer epic id sharing this prefix, not
        # a hyphen-suffixed variant of this same epic id.
        _init_git_repo_with_remote_branch(tmp_path, "dev/claude/ADR-369-spec-stack")

        # Act & Assert
        assert _real_feature_branch_exists("ADR-369", tmp_path) is True

    def test_feature_branch_exists_prefix_of_a_different_epic_id_returns_false(self, tmp_path):
        # Arrange — regression test for the unanchored substring bug: `dev/claude/ADR-3690-spec`
        # (a different epic's branch) must not be mistaken for `ADR-369`'s own branch.
        _init_git_repo_with_remote_branch(tmp_path, "dev/claude/ADR-3690-spec")

        # Act & Assert
        assert _real_feature_branch_exists("ADR-369", tmp_path) is False

    def test_feature_branch_exists_no_matching_branch_returns_false(self, tmp_path):
        # Arrange
        _init_git_repo_with_remote_branch(tmp_path, "dev/claude/ADR-999-spec")

        # Act & Assert
        assert _real_feature_branch_exists("ADR-369", tmp_path) is False

    def test_feature_branch_exists_git_command_failure_raises_runtime_error(self, tmp_path):
        # Arrange — `tmp_path` is not a git repository at all, so `git branch -r` fails
        # (returncode 128, "fatal: not a git repository" on stderr) rather than returning empty
        # output for "no such branch"; that failure must surface, not be swallowed as False.

        # Act & Assert
        with pytest.raises(RuntimeError, match="git branch -r"):
            _real_feature_branch_exists("ADR-369", tmp_path)


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
        assert result["spawn"] == [{"task_id": "ADR-1"}]
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
        _write_spec(tmp_path, {"ADR-2": [], "ADR-1": ["ADR-2"]})
        _save_context("ADR-2", state="done")
        from concurrent_schedule import TargetSpec, compute_next_batch, poll_until_actionable

        target = TargetSpec(mode="up_to", tasks=("ADR-1",))
        # First real poll (outside the function, to seed "spawned") — simulate ADR-1 already
        # spawned so the very first internal poll comes back idle ("waiting", empty spawn).
        first = compute_next_batch(target)
        assert first["spawn"] == [{"task_id": "ADR-1"}]
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
        _write_spec(tmp_path, {"ADR-2": [], "ADR-1": ["ADR-2"]})
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
        assert result["spawn"] == [{"task_id": "ADR-7"}]


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
        # Arrange — a real minimal git repo whose `git branch -r` output already includes the
        # epic's feature branch, so the live bootstrap check (which can't be monkeypatched
        # across this subprocess boundary) finds it bootstrapped, exactly as it would in a real
        # checkout. This also gives `dev_team.py`'s own repo-root discovery a genuine `.git` to
        # resolve to `tmp_path` (where the fake spec lives).
        _write_spec(tmp_path, {"ADR-1": []})
        _init_git_repo_with_remote_branch(tmp_path, f"dev/claude/{_DEFAULT_EPIC_ID}-spec")
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
            "spawn": [{"task_id": "ADR-1"}],
            "blocked_tasks": [],
            "running": [],
        }

    def test_main_list_dependency_outside_list_and_not_done_prints_error_and_exits_nonzero(
        self, tmp_path
    ):
        # Arrange
        (tmp_path / ".git").mkdir()
        _write_spec(tmp_path, {"ADR-2": [], "ADR-1": ["ADR-2"]})
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
