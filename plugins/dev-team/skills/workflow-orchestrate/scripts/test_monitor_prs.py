"""Tests for monitor_prs.py — the long-lived PR monitor pipeline steps built on dev_team.py's
generic engine.

Covers:
- BootstrappingStep / SyncingStackStep / ScanningStackEventsStep / ContinuingRebaseStep /
  PrPollStep — get_actions()/handle_results() shape, and each one's failure self-loop
  (reachable on exit-0-but-unparseable content, not a script crash — a genuine crash is caught
  generically by workflow-orchestrate's own dispatch check before handle_results() ever runs)
- ResolvingConflictStep — conflicting-task-id derivation, the merge_pending_deliverables-on-a-
  foreign-file regression fix, and the resolved/unresolved/agent_failed verdict handling
- CleaningUpStep — own_worktree branching and cleanup-failure handling
- ReactStep / NotifyStep — shared stack/PR-mode reactions, dispatched against a task's own
  context file, and the new "notify" action verb's exact shape
- Structural invariants on monitor-stack-plan.md / monitor-pr-plan.md (self-loops present, PR
  mode lacks the stack-only states)
- Roundtrip save/load for every new PipelineContext field
"""

import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPTS_DIR.parent / "assets"


def _make_ctx(**kwargs):
    from pipeline_context import PipelineContext
    kwargs.setdefault("work_item_id", "EPIC-1")
    return PipelineContext(**kwargs)


# ---------------------------------------------------------------------------
# New PipelineContext fields — roundtrip
# ---------------------------------------------------------------------------

class TestNewContextFieldsRoundtrip:
    def test_own_worktree_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(work_item_id="EPIC-1", own_worktree=True)
        path = tmp_path / "ctx.md"
        ctx.save(path)
        assert PipelineContext.load(path).own_worktree is True

    def test_own_worktree_defaults_false(self):
        assert _make_ctx().own_worktree is False

    def test_watch_worktree_path_and_branch_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(
            work_item_id="EPIC-1",
            watch_worktree_path="/some/wt",
            watch_worktree_branch="dev/x/EPIC-1",
        )
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.watch_worktree_path == "/some/wt"
        assert loaded.watch_worktree_branch == "dev/x/EPIC-1"

    def test_pr_numbers_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(work_item_id="watch-pr-1-2", pr_numbers="1,2")
        path = tmp_path / "ctx.md"
        ctx.save(path)
        assert PipelineContext.load(path).pr_numbers == "1,2"

    def test_poll_event_task_id_and_conflicting_task_id_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(
            work_item_id="EPIC-1", poll_event_task_id="TASK-5", conflicting_task_id="TASK-6",
        )
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.poll_event_task_id == "TASK-5"
        assert loaded.conflicting_task_id == "TASK-6"

    def test_post_handoff_fix_count_and_rebase_conflict_count_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(
            work_item_id="EPIC-1", post_handoff_fix_count=2, rebase_conflict_count=1,
        )
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.post_handoff_fix_count == 2
        assert loaded.rebase_conflict_count == 1

    def test_pending_user_question_roundtrip(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(work_item_id="EPIC-1", pending_user_question="What now?")
        path = tmp_path / "ctx.md"
        ctx.save(path)
        assert PipelineContext.load(path).pending_user_question == "What now?"

    def test_poll_result_roundtrip_via_body_section(self, tmp_path):
        from pipeline_context import PipelineContext
        ctx = PipelineContext(work_item_id="EPIC-1", poll_result='{"event": "ci_failure"}')
        path = tmp_path / "ctx.md"
        ctx.save(path)
        loaded = PipelineContext.load(path)
        assert loaded.poll_result == '{"event": "ci_failure"}'


# ---------------------------------------------------------------------------
# BootstrappingStep
# ---------------------------------------------------------------------------

class TestBootstrappingStep:
    def test_passthrough_when_not_own_worktree(self, tmp_path):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=False)
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.get_actions() == []
        assert step.handle_results() == "ready"

    def test_dispatches_run_script_when_own_worktree(self, tmp_path):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=True)
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        actions = step.get_actions()
        assert len(actions) == 1
        assert actions[0]["action"] == "run_script"
        assert "stack_bootstrap.py" in actions[0]["command"]
        assert actions[0]["write_section"] == "Poll Result"

    def test_no_dispatch_once_poll_result_present(self, tmp_path):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=True, poll_result='"ok"')
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.get_actions() == []

    def test_handle_results_ready_on_ok(self, tmp_path, monkeypatch):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=True, poll_result='"ok"')
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="/some/wt\n"),
        )
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        trigger = step.handle_results()
        assert trigger == "ready"
        assert ctx.poll_result == ""
        assert ctx.watch_worktree_path == "/some/wt"

    def test_handle_results_checkout_failed_on_unparseable(self, tmp_path):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=True, poll_result="not json")
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "checkout_failed"
        assert ctx.consecutive_failures == 1

    def test_handle_results_checkout_failed_when_missing(self, tmp_path):
        from monitor_prs import BootstrappingStep
        ctx = _make_ctx(own_worktree=True)
        step = BootstrappingStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "checkout_failed"


# ---------------------------------------------------------------------------
# SyncingStackStep
# ---------------------------------------------------------------------------

class TestSyncingStackStep:
    def test_dispatches_stack_sync(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx()
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        actions = step.get_actions()
        assert len(actions) == 1
        assert "stack_sync.py" in actions[0]["command"]

    def test_no_dispatch_once_poll_result_present(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx(poll_result='"synced"')
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.get_actions() == []

    def test_handle_results_synced(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx(poll_result='"synced"')
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "synced"
        assert ctx.poll_result == ""
        assert ctx.consecutive_failures == 0

    def test_handle_results_conflict(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx(poll_result='"conflict"')
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "conflict"

    def test_handle_results_sync_failed_on_unparseable(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx(poll_result="garbled")
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "sync_failed"
        assert ctx.consecutive_failures == 1

    def test_handle_results_sync_failed_when_missing(self, tmp_path):
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx()
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "sync_failed"

    def test_repeated_failures_escalate_to_troubleshooter(self, tmp_path):
        """Mirrors the generic consecutive_failures/CONSECUTIVE_FAILURES_THRESHOLD mechanism
        every other Step in the codebase already relies on for the same purpose."""
        import dev_team
        from monitor_prs import SyncingStackStep
        ctx = _make_ctx(consecutive_failures=dev_team.CONSECUTIVE_FAILURES_THRESHOLD - 1)
        step = SyncingStackStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        with pytest.raises(SystemExit) as exc_info:
            step.handle_results()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# ScanningStackEventsStep
# ---------------------------------------------------------------------------

class TestScanningStackEventsStep:
    def test_dispatches_stack_scan(self, tmp_path):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx()
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        actions = step.get_actions()
        assert len(actions) == 1
        assert "stack_scan.py" in actions[0]["command"]

    def test_handle_results_no_change(self, tmp_path):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx(poll_result='"no_change"')
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "no_change"

    def test_handle_results_stack_complete(self, tmp_path):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx(poll_result='"stack_complete"')
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "stack_complete"

    @pytest.mark.parametrize("event", ["review_comment", "ci_failure", "human_comment"])
    def test_handle_results_event_sets_poll_event_task_id(self, tmp_path, event):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx(poll_result=json.dumps({"task_work_item_id": "TASK-9", "event": event}))
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        trigger = step.handle_results()
        assert trigger == event
        assert ctx.poll_event_task_id == "TASK-9"

    def test_handle_results_scan_failed_on_unparseable(self, tmp_path):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx(poll_result="garbled")
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "scan_failed"

    def test_handle_results_scan_failed_on_malformed_event_object(self, tmp_path):
        from monitor_prs import ScanningStackEventsStep
        ctx = _make_ctx(poll_result=json.dumps({"unexpected": "shape"}))
        step = ScanningStackEventsStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "scan_failed"


# ---------------------------------------------------------------------------
# PrPollStep
# ---------------------------------------------------------------------------

class TestPrPollStep:
    def test_dispatches_pr_list_poll_with_pr_numbers(self, tmp_path):
        from monitor_prs import PrPollStep
        ctx = _make_ctx(work_item_id="watch-pr-1-2", pr_numbers="1,2")
        step = PrPollStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        actions = step.get_actions()
        assert len(actions) == 1
        assert "pr_list_poll.py" in actions[0]["command"]
        assert '"1,2"' in actions[0]["command"]

    def test_handle_results_all_complete(self, tmp_path):
        from monitor_prs import PrPollStep
        ctx = _make_ctx(poll_result='"all_complete"')
        step = PrPollStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "all_complete"

    def test_handle_results_no_change(self, tmp_path):
        from monitor_prs import PrPollStep
        ctx = _make_ctx(poll_result='"no_change"')
        step = PrPollStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "no_change"

    def test_handle_results_event(self, tmp_path):
        from monitor_prs import PrPollStep
        ctx = _make_ctx(poll_result=json.dumps({"task_work_item_id": "TASK-3", "event": "ci_failure"}))
        step = PrPollStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "ci_failure"
        assert ctx.poll_event_task_id == "TASK-3"

    def test_handle_results_poll_failed_on_unparseable(self, tmp_path):
        from monitor_prs import PrPollStep
        ctx = _make_ctx(poll_result="garbled")
        step = PrPollStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "poll_failed"


# ---------------------------------------------------------------------------
# ContinuingRebaseStep
# ---------------------------------------------------------------------------

class TestContinuingRebaseStep:
    def test_dispatches_stack_rebase_continue(self, tmp_path):
        from monitor_prs import ContinuingRebaseStep
        ctx = _make_ctx()
        step = ContinuingRebaseStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        actions = step.get_actions()
        assert len(actions) == 1
        assert "stack_rebase_continue.py" in actions[0]["command"]

    def test_handle_results_ok_clears_conflicting_task_id(self, tmp_path):
        from monitor_prs import ContinuingRebaseStep
        ctx = _make_ctx(poll_result='"ok"', conflicting_task_id="TASK-7")
        step = ContinuingRebaseStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "ok"
        assert ctx.conflicting_task_id == ""

    def test_handle_results_conflict(self, tmp_path):
        from monitor_prs import ContinuingRebaseStep
        ctx = _make_ctx(poll_result='"conflict"')
        step = ContinuingRebaseStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "conflict"

    def test_handle_results_continue_failed_on_unparseable(self, tmp_path):
        from monitor_prs import ContinuingRebaseStep
        ctx = _make_ctx(poll_result="garbled")
        step = ContinuingRebaseStep(ctx, tmp_path / "ctx.md", tmp_path / "logs")
        assert step.handle_results() == "continue_failed"


# ---------------------------------------------------------------------------
# CleaningUpStep
# ---------------------------------------------------------------------------

class TestCleaningUpStep:
    def test_cleaned_immediately_when_not_own_worktree(self, tmp_path):
        from monitor_prs import CleaningUpStep
        ctx = _make_ctx(own_worktree=False)
        step = CleaningUpStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []
        assert step.handle_results() == "cleaned"

    def test_removes_worktree_and_branch_when_own_worktree(self, tmp_path, monkeypatch):
        from monitor_prs import CleaningUpStep
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="/main/.git\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        ctx = _make_ctx(
            own_worktree=True, watch_worktree_path="/wt", watch_worktree_branch="dev/x/EPIC-1",
        )
        step = CleaningUpStep(ctx, tmp_path / "ctx.md")
        assert step.handle_results() == "cleaned"
        assert any(c[:3] == ["git", "worktree", "remove"] for c in calls)
        assert any(c[:3] == ["git", "branch", "-D"] for c in calls)

    def test_cleanup_failed_never_reports_cleaned(self, tmp_path, monkeypatch):
        from monitor_prs import CleaningUpStep

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "rev-parse"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="/main/.git\n")
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(subprocess, "run", fake_run)
        ctx = _make_ctx(own_worktree=True, watch_worktree_path="/wt", watch_worktree_branch="dev/x/EPIC-1")
        step = CleaningUpStep(ctx, tmp_path / "ctx.md")
        assert step.handle_results() == "cleanup_failed"
        assert ctx.consecutive_failures == 1


# ---------------------------------------------------------------------------
# ReactStep / NotifyStep (shared, stack + PR mode)
# ---------------------------------------------------------------------------

class TestReactStep:
    def test_no_dispatch_without_poll_event_task_id(self, tmp_path):
        from monitor_prs import ReactStep
        ctx = _make_ctx()
        step = ReactStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []

    def test_dispatches_fix_pr_against_task_context_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import ReactStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug

        ctx = _make_ctx(poll_event_task_id="TASK-5", post_handoff_fix_count=0)
        step = ReactStep(ctx, tmp_path / "monitor-ctx.md")
        actions = step.get_actions()
        assert len(actions) == 1
        action = actions[0]
        assert action["action"] == "spawn_agent"
        assert action["skill"] == "fix-pr"
        assert action["args"] == "TASK-5"
        assert action["write_section"] == "Post-Handoff Fix 1"
        expected_task_path = str(compute_context_path("TASK-5", get_repo_slug()))
        assert action["context_file"] == expected_task_path

    def test_no_redispatch_once_pending_agent_set(self, tmp_path):
        from monitor_prs import ReactStep
        ctx = _make_ctx(poll_event_task_id="TASK-5", pending_agent="reacting_fix")
        step = ReactStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []

    def test_handle_results_merges_pending_deliverables_and_increments_counter(
        self, tmp_path, monkeypatch,
    ):
        """Regression test for the required merge_pending_deliverables fix: nothing else ever
        re-invokes the pipeline for the *task's own* work_item_id, so ReactStep must merge its
        own scratch deliverable itself."""
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import ReactStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        task_id = "TASK-5"
        task_path = compute_context_path(task_id, get_repo_slug())
        PipelineContext(work_item_id=task_id).save(task_path)
        pending_dir = task_path.parent / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / f"{task_id}__Post-Handoff_Fix_1.md").write_text(
            "fixed it", encoding="utf-8",
        )

        ctx = _make_ctx(poll_event_task_id=task_id, post_handoff_fix_count=0)
        step = ReactStep(ctx, tmp_path / "monitor-ctx.md")
        trigger = step.handle_results()

        assert trigger == "reacted"
        assert ctx.post_handoff_fix_count == 1
        assert ctx.poll_event_task_id == ""
        assert ctx.pending_agent == ""
        merged_text = task_path.read_text(encoding="utf-8")
        assert "fixed it" in merged_text
        assert not (pending_dir / f"{task_id}__Post-Handoff_Fix_1.md").exists()


class TestNotifyStep:
    def test_no_dispatch_without_poll_event_task_id(self, tmp_path):
        from monitor_prs import NotifyStep
        ctx = _make_ctx()
        step = NotifyStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []

    def test_notify_action_shape(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import NotifyStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        task_id = "TASK-8"
        task_path = compute_context_path(task_id, get_repo_slug())
        PipelineContext(work_item_id=task_id, pr_url="https://github.com/x/y/pull/1").save(task_path)

        ctx = _make_ctx(poll_event_task_id=task_id)
        step = NotifyStep(ctx, tmp_path / "monitor-ctx.md")
        actions = step.get_actions()
        assert actions == [{
            "action": "notify",
            "message": f"Human comment on {task_id}'s PR needs a response: https://github.com/x/y/pull/1",
        }]

    def test_no_redispatch_once_pending_agent_set(self, tmp_path):
        from monitor_prs import NotifyStep
        ctx = _make_ctx(poll_event_task_id="TASK-8", pending_agent="notifying")
        step = NotifyStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []

    def test_handle_results_clears_state_and_returns_notified(self, tmp_path):
        from monitor_prs import NotifyStep
        ctx = _make_ctx(poll_event_task_id="TASK-8", pending_agent="notifying")
        step = NotifyStep(ctx, tmp_path / "ctx.md")
        assert step.handle_results() == "notified"
        assert ctx.poll_event_task_id == ""
        assert ctx.pending_agent == ""


# ---------------------------------------------------------------------------
# ResolvingConflictStep
# ---------------------------------------------------------------------------

class TestResolvingConflictStep:
    def test_no_redispatch_once_pending_agent_set(self, tmp_path):
        from monitor_prs import ResolvingConflictStep
        ctx = _make_ctx(pending_agent="resolving_conflict")
        step = ResolvingConflictStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []

    def test_get_actions_agent_failed_when_conflict_id_undeterminable(self, tmp_path, monkeypatch):
        from monitor_prs import ResolvingConflictStep
        import monitor_prs

        def raise_error():
            raise RuntimeError("no rebase-merge/rebase-apply head-name file found")

        monkeypatch.setattr(monitor_prs, "_conflicting_task_id", raise_error)
        ctx = _make_ctx()
        step = ResolvingConflictStep(ctx, tmp_path / "ctx.md")
        assert step.get_actions() == []
        assert ctx.consecutive_failures == 1

    def test_get_actions_dispatches_resolve_rebase_conflict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        import monitor_prs
        from monitor_prs import ResolvingConflictStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        monkeypatch.setattr(monitor_prs, "_conflicting_task_id", lambda: "TASK-9")
        task_path = compute_context_path("TASK-9", get_repo_slug())
        PipelineContext(work_item_id="TASK-9", brief="the task brief").save(task_path)

        ctx = _make_ctx(rebase_conflict_count=0)
        step = ResolvingConflictStep(ctx, tmp_path / "monitor-ctx.md")
        actions = step.get_actions()
        assert len(actions) == 1
        action = actions[0]
        assert action["skill"] == "resolve-rebase-conflict"
        assert action["args"] == "the task brief"
        assert action["write_section"] == "Rebase Conflict 1"
        assert action["context_file"] == str(task_path)
        assert ctx.conflicting_task_id == "TASK-9"

    def test_handle_results_resolved_merges_deliverable_and_increments_counter(
        self, tmp_path, monkeypatch,
    ):
        """Regression test: resolve-rebase-conflict's own verdict is written to the task's own
        context file as a scratch deliverable — nothing re-invokes the pipeline for that task's
        own work_item_id, so handle_results() must merge it in itself before reading the verdict
        back, or it would always see stale (empty) content."""
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import ResolvingConflictStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        task_id = "TASK-9"
        task_path = compute_context_path(task_id, get_repo_slug())
        PipelineContext(work_item_id=task_id).save(task_path)
        pending_dir = task_path.parent / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / f"{task_id}__Rebase_Conflict_1.md").write_text(
            "resolved", encoding="utf-8",
        )

        ctx = _make_ctx(conflicting_task_id=task_id, rebase_conflict_count=0)
        step = ResolvingConflictStep(ctx, tmp_path / "monitor-ctx.md")
        trigger = step.handle_results()

        assert trigger == "resolved"
        assert ctx.rebase_conflict_count == 1
        assert not (pending_dir / f"{task_id}__Rebase_Conflict_1.md").exists()

    def test_handle_results_unresolved(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import ResolvingConflictStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        task_id = "TASK-10"
        task_path = compute_context_path(task_id, get_repo_slug())
        PipelineContext(work_item_id=task_id).save(task_path)
        pending_dir = task_path.parent / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / f"{task_id}__Rebase_Conflict_1.md").write_text(
            "unresolved", encoding="utf-8",
        )

        ctx = _make_ctx(conflicting_task_id=task_id, rebase_conflict_count=0)
        step = ResolvingConflictStep(ctx, tmp_path / "monitor-ctx.md")
        assert step.handle_results() == "unresolved"
        assert ctx.rebase_conflict_count == 1

    def test_handle_results_agent_failed_on_missing_verdict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEV_TEAM_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("GIT_REMOTE_URL_OVERRIDE", "https://github.com/example/repo.git")
        from monitor_prs import ResolvingConflictStep
        from dev_team import compute_context_path
        from get_context_path import get_repo_slug
        from pipeline_context import PipelineContext

        task_id = "TASK-11"
        task_path = compute_context_path(task_id, get_repo_slug())
        PipelineContext(work_item_id=task_id).save(task_path)

        ctx = _make_ctx(conflicting_task_id=task_id, rebase_conflict_count=0)
        step = ResolvingConflictStep(ctx, tmp_path / "monitor-ctx.md")
        assert step.handle_results() == "agent_failed"
        assert ctx.consecutive_failures == 1


# ---------------------------------------------------------------------------
# _conflicting_task_id
# ---------------------------------------------------------------------------

class TestConflictingTaskId:
    def test_derives_from_rebase_merge_head_name(self, tmp_path, monkeypatch):
        from monitor_prs import _conflicting_task_id
        import monitor_prs

        git_dir = tmp_path / ".git"
        (git_dir / "rebase-merge").mkdir(parents=True)
        (git_dir / "rebase-merge" / "head-name").write_text(
            "refs/heads/dev/claude/ADR-380\n", encoding="utf-8",
        )

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "rev-parse", "--git-dir"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=str(git_dir) + "\n")
            raise AssertionError(f"unexpected command {cmd}")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _conflicting_task_id() == "ADR-380"

    def test_falls_back_to_rebase_apply(self, tmp_path, monkeypatch):
        from monitor_prs import _conflicting_task_id

        git_dir = tmp_path / ".git"
        (git_dir / "rebase-apply").mkdir(parents=True)
        (git_dir / "rebase-apply" / "head-name").write_text(
            "refs/heads/dev/claude/Issue-99-some-slug\n", encoding="utf-8",
        )

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=str(git_dir) + "\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert _conflicting_task_id() == "Issue-99"

    def test_raises_when_neither_rebase_dir_exists(self, tmp_path, monkeypatch):
        from monitor_prs import _conflicting_task_id

        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout=str(git_dir) + "\n")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError):
            _conflicting_task_id()


# ---------------------------------------------------------------------------
# step_handlers factory — every mermaid state has a handler
# ---------------------------------------------------------------------------

class TestBuildStepHandlers:
    def test_covers_every_stack_plan_state(self, tmp_path):
        import dev_team
        import monitor_prs

        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        states = {s for d in wf.transitions.values() for s in d.values()} | set(wf.transitions)
        states -= wf.terminal_states
        states.discard(wf.initial_state)

        handlers = monitor_prs._build_step_handlers(
            _make_ctx(), tmp_path / "ctx.md", tmp_path / "logs",
        )
        assert states <= set(handlers.keys())

    def test_covers_every_pr_plan_state(self, tmp_path):
        import dev_team
        import monitor_prs

        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-pr-plan.md")
        states = {s for d in wf.transitions.values() for s in d.values()} | set(wf.transitions)
        states -= wf.terminal_states
        states.discard(wf.initial_state)

        handlers = monitor_prs._build_step_handlers(
            _make_ctx(), tmp_path / "ctx.md", tmp_path / "logs",
        )
        assert states <= set(handlers.keys())


# ---------------------------------------------------------------------------
# Structural invariants on the mermaid assets themselves
# ---------------------------------------------------------------------------

class TestWorkflowAssetMonitorStructural:
    def test_stack_plan_has_no_change_self_loop(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        assert wf.transitions["scanning_stack_events"]["no_change"] == "syncing_stack"

    def test_pr_plan_has_no_change_self_loop(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-pr-plan.md")
        assert wf.transitions["polling_pr"]["no_change"] == "polling_pr"

    @pytest.mark.parametrize("state,trigger", [
        ("bootstrapping", "checkout_failed"),
        ("syncing_stack", "sync_failed"),
        ("scanning_stack_events", "scan_failed"),
        ("resolving_conflict", "agent_failed"),
        ("continuing_rebase", "continue_failed"),
        ("cleaning_up", "cleanup_failed"),
    ])
    def test_stack_plan_failure_self_loops_exist(self, state, trigger):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        assert wf.transitions[state][trigger] == state

    def test_pr_plan_poll_failed_self_loop_exists(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-pr-plan.md")
        assert wf.transitions["polling_pr"]["poll_failed"] == "polling_pr"

    def test_reacting_fix_and_notifying_present_in_both_assets(self):
        """Both assets route review_comment/ci_failure -> reacting_fix and
        human_comment -> notifying — the one shared Step class both poll paths dispatch into via
        ctx.poll_event_task_id. Each routes its own "reacted"/"notified" trigger back to its own
        mode's poll entry state (syncing_stack vs polling_pr), so the transition *targets*
        legitimately differ — only the trigger *names* and the fact that both states exist in
        both assets is shared."""
        import dev_team
        stack_wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        pr_wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-pr-plan.md")
        assert set(stack_wf.transitions["reacting_fix"]) == set(pr_wf.transitions["reacting_fix"]) == {"reacted"}
        assert set(stack_wf.transitions["notifying"]) == set(pr_wf.transitions["notifying"]) == {"notified"}
        assert stack_wf.transitions["reacting_fix"]["reacted"] == "syncing_stack"
        assert pr_wf.transitions["reacting_fix"]["reacted"] == "polling_pr"

    def test_pr_plan_lacks_stack_only_states(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-pr-plan.md")
        all_states = set(wf.transitions) | {
            s for d in wf.transitions.values() for s in d.values()
        }
        stack_only = {
            "bootstrapping", "syncing_stack", "scanning_stack_events",
            "resolving_conflict", "continuing_rebase", "cleaning_up", "failed",
        }
        assert not (all_states & stack_only)

    def test_stack_plan_reaches_done_only_via_cleaning_up(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        sources_of_done = [
            src for src, triggers in wf.transitions.items()
            if "done" in triggers.values()
        ]
        assert sources_of_done == ["cleaning_up"]

    def test_stack_plan_unresolved_reaches_failed(self):
        import dev_team
        wf = dev_team.parse_workflow(ASSETS_DIR / "monitor-stack-plan.md")
        assert wf.transitions["resolving_conflict"]["unresolved"] == "failed"
