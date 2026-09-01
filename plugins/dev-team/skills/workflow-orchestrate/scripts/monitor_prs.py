#!/usr/bin/env python3
"""Long-lived PR monitor pipeline steps — stack mode (`monitor-stack-plan.md`) and PR mode
(`monitor-pr-plan.md`).

Entry point: main() — accepts a work item id (an epic id for stack mode, or a synthetic
`watch-pr-<sorted-pr-numbers>` key for PR mode) and context file path, runs the monitor
pipeline until an agent/script is needed or a poll cycle needs to wait, then exits with a JSON
descriptor on stdout (exit code 0). The workflow-orchestrate skill re-invokes this script after
each dispatch, exactly as it does for implement.py.

Unlike implement.py's task pipeline, this pipeline's steady state is a long-lived poll loop with
no natural "done" until every monitored PR merges (or, stack mode only, an unresolved rebase
conflict halts it) — see monitor-stack-plan.md/monitor-pr-plan.md's `no_change` self-transitions.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import dev_team
from dev_team import (
    REPO_ROOT,
    CONSECUTIVE_FAILURES_THRESHOLD,
    Step,
    _check_and_trigger_troubleshooter,
    _handle_agent_failure,
    _handle_agent_success,
    _parse_frontmatter,
    _parse_sections,
    compute_context_path,
    merge_pending_deliverables,
)
from detect_next_stack_event import _WORK_ITEM_ID_RE  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_context_path(task_work_item_id: str) -> Path:
    """Compute a task's own context file path — distinct from this monitor's own, since
    ReactStep/NotifyStep/ResolvingConflictStep all act on some other task's PR/branch, not the
    monitor's own work item."""
    return compute_context_path(task_work_item_id, get_repo_slug())


def _load_task_context(task_work_item_id: str) -> PipelineContext | None:
    path = _task_context_path(task_work_item_id)
    if not path.exists():
        return None
    return PipelineContext.load(path)


def _new_log_path(log_dir: Path, work_item_id: str, label: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return log_dir / f"{work_item_id}-{label}-{timestamp}.log"


def _parse_poll_json(raw: str):
    """Parse a poll/sync/scan/rebase-continue script's bare JSON result (already extracted
    verbatim by workflow-script's step 2 into the Poll Result section). Returns None if the
    content isn't valid JSON at all — a genuine content anomaly a Step's own handle_results()
    must fall back on, distinct from a script crash (which never reaches this file at all —
    caught by workflow-orchestrate's own generic dispatch-result check first)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _conflicting_task_id() -> str:
    """Determine which task's branch a `gh stack sync`/`stack_rebase_continue.py` cascade left
    mid-rebase, from the standard `.git/rebase-merge`/`.git/rebase-apply` state — mirrors
    resolve-rebase-conflict's own convention, and detect_next_stack_event.py's
    `name.rsplit("/", 1)[-1]` + `_WORK_ITEM_ID_RE` convention for extracting a work item id from
    a branch's last path segment."""
    git_dir_str = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    git_dir = Path(git_dir_str)
    if not git_dir.is_absolute():
        git_dir = REPO_ROOT / git_dir
    head_name_file = git_dir / "rebase-merge" / "head-name"
    if not head_name_file.is_file():
        head_name_file = git_dir / "rebase-apply" / "head-name"
    if not head_name_file.is_file():
        raise RuntimeError("no rebase-merge/rebase-apply head-name file found")

    ref = head_name_file.read_text(encoding="utf-8").strip()
    branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    last_segment = branch.rsplit("/", 1)[-1]
    match = _WORK_ITEM_ID_RE.match(last_segment)
    return match.group(0) if match else last_segment


def _read_task_section(task_context_path: Path, section_name: str) -> str:
    """Read a single section directly from a task's own context file's raw text — used for the
    resolve-rebase-conflict verdict, which merge_pending_deliverables() has already merged in by
    the time this is called."""
    if not task_context_path.exists():
        return ""
    text = task_context_path.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(text)
    sections = _parse_sections(body)
    return sections.get(section_name, "")


# ---------------------------------------------------------------------------
# Stack-mode steps
# ---------------------------------------------------------------------------

class BootstrappingStep(Step):
    """Bootstraps `gh stack` awareness into a freshly auto-started monitor's own worktree
    (`ctx.own_worktree`), then records that worktree's own path/branch for later cleanup — this
    is what used to be monitor-prs's own prose steps 2a/3, now a real dispatched state since the
    epic id (this pipeline's own work_item_id) is already known by the time this state runs.
    For `/watch-stack`'s in-session path (`not ctx.own_worktree`, already on a real stack member
    branch), this is a no-op passthrough."""

    handles = "bootstrapping"
    _PENDING_KEY = "bootstrapping"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if not ctx.own_worktree:
            return []
        if ctx.poll_result:
            return []
        script = Path(__file__).parent / "stack_bootstrap.py"
        command = f'{sys.executable} "{script}" "{ctx.work_item_id}" "{self._context_path}"'
        log_path = _new_log_path(self._log_dir, ctx.work_item_id, "bootstrap")
        return [{
            "action": "run_script",
            "message": f"Bootstrapping gh-stack awareness for epic {ctx.work_item_id}.",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Poll Result",
            "result_format": '"ok"',
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.own_worktree:
            return "ready"
        if not ctx.poll_result:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "checkout_failed"

        result = _parse_poll_json(ctx.poll_result.strip())
        ctx.poll_result = ""
        ctx.pending_agent = ""
        if result != "ok":
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "checkout_failed"

        _handle_agent_success(ctx)
        ctx.watch_worktree_path = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        ctx.watch_worktree_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return "ready"


class SyncingStackStep(Step):
    """Runs `gh stack sync` via `stack_sync.py`. `"conflict"` routes to `resolving_conflict`; a
    genuine content anomaly (exit 0 but unparseable/unexpected output — a script crash is caught
    generically by workflow-orchestrate's own dispatch check before this is ever reached) retries
    in place via `sync_failed`, escalating through the standard `consecutive_failures`
    mechanism."""

    handles = "syncing_stack"
    _PENDING_KEY = "syncing_stack"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.poll_result:
            return []
        script = Path(__file__).parent / "stack_sync.py"
        command = f'{sys.executable} "{script}"'
        log_path = _new_log_path(self._log_dir, ctx.work_item_id, "sync")
        return [{
            "action": "run_script",
            "message": "Syncing the stack (gh stack sync).",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Poll Result",
            "result_format": '"synced" | "conflict"',
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.poll_result:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "sync_failed"

        result = _parse_poll_json(ctx.poll_result.strip())
        ctx.poll_result = ""
        ctx.pending_agent = ""
        if result == "synced":
            _handle_agent_success(ctx)
            return "synced"
        if result == "conflict":
            _handle_agent_success(ctx)
            return "conflict"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "sync_failed"


class ScanningStackEventsStep(Step):
    """Runs `detect_next_stack_event()` via `stack_scan.py` — the review-comment/CI-failure/
    human-comment/merge scan across the whole stack. `scan_failed` mirrors `SyncingStackStep`'s
    own failure handling exactly."""

    handles = "scanning_stack_events"
    _PENDING_KEY = "scanning_stack_events"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.poll_result:
            return []
        script = Path(__file__).parent / "stack_scan.py"
        command = f'{sys.executable} "{script}"'
        log_path = _new_log_path(self._log_dir, ctx.work_item_id, "scan")
        return [{
            "action": "run_script",
            "message": "Scanning the stack for review comments, CI failures, and merges.",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Poll Result",
            "result_format": '"no_change" | "stack_complete" | {"task_work_item_id","event"}',
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.poll_result:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "scan_failed"

        result = _parse_poll_json(ctx.poll_result.strip())
        ctx.poll_result = ""
        ctx.pending_agent = ""
        if result == "no_change":
            _handle_agent_success(ctx)
            return "no_change"
        if result == "stack_complete":
            _handle_agent_success(ctx)
            return "stack_complete"
        if isinstance(result, dict) and "task_work_item_id" in result and "event" in result:
            _handle_agent_success(ctx)
            ctx.poll_event_task_id = result["task_work_item_id"]
            return result["event"]
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "scan_failed"


class ResolvingConflictStep(Step):
    """Resolves one rebase conflict the `gh stack sync` cascade hit, via the developer agent's
    `resolve-rebase-conflict` skill, dispatched against the *conflicting task's own* context
    file — never this monitor's own. `agent_failed` covers both a failure to determine which
    task is conflicting (native git-plumbing failure) and a spawn that reported dispatch-level
    success but wrote neither `resolved` nor `unresolved` (a content anomaly, mirroring
    DebugStep's "agent ran but wrote nothing" fallback) — a genuine spawn failure is caught
    generically by workflow-orchestrate before this is ever reached, the same as every other
    agent-spawn step in the codebase."""

    handles = "resolving_conflict"
    _PENDING_KEY = "resolving_conflict"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.pending_agent == "resolving_conflict":
            return []

        try:
            conflicting_task_id = _conflicting_task_id()
        except (RuntimeError, subprocess.CalledProcessError):
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return []

        ctx.conflicting_task_id = conflicting_task_id
        task_context_path = _task_context_path(conflicting_task_id)
        # Defensive: covers a prior crashed attempt at this same conflict leaving a scratch
        # file behind that was never merged.
        merge_pending_deliverables(task_context_path, conflicting_task_id)
        task_ctx = _load_task_context(conflicting_task_id)
        brief = task_ctx.brief if task_ctx else ""
        section = f"Rebase Conflict {ctx.rebase_conflict_count + 1}"
        return [{
            "action": "spawn_agent",
            "message": f"Resolving a rebase conflict on {conflicting_task_id}'s branch.",
            "agent": "dev-team:developer",
            "skill": "resolve-rebase-conflict",
            "args": brief,
            "context_file": str(task_context_path),
            "read_sections": [],
            "write_section": section,
            "result_format": "resolved | unresolved",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        task_id = ctx.conflicting_task_id
        task_context_path = _task_context_path(task_id)
        # Required fix (see plan Context): merge the scratch deliverable the spawned agent
        # wrote before reading its verdict back — nothing else ever re-invokes the pipeline for
        # this *task's own* work_item_id to do this merge otherwise.
        merge_pending_deliverables(task_context_path, task_id)
        section = f"Rebase Conflict {ctx.rebase_conflict_count + 1}"
        verdict = _read_task_section(task_context_path, section).strip()
        ctx.pending_agent = ""

        if verdict == "resolved":
            _handle_agent_success(ctx)
            ctx.rebase_conflict_count += 1
            return "resolved"
        if verdict == "unresolved":
            _handle_agent_success(ctx)
            ctx.rebase_conflict_count += 1
            return "unresolved"

        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "agent_failed"


class ContinuingRebaseStep(Step):
    """Resumes the `gh stack` rebase cascade after one branch's conflict was resolved, via
    `stack_rebase_continue.py` — completing only the conflicting branch's own rebase isn't
    enough to reconcile a multi-branch stack (ADR-370's spike, section 3)."""

    handles = "continuing_rebase"
    _PENDING_KEY = "continuing_rebase"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.poll_result:
            return []
        script = Path(__file__).parent / "stack_rebase_continue.py"
        command = f'{sys.executable} "{script}"'
        log_path = _new_log_path(self._log_dir, ctx.work_item_id, "rebase-continue")
        return [{
            "action": "run_script",
            "message": "Resuming the stack's rebase cascade.",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Poll Result",
            "result_format": '"ok" | "conflict"',
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.poll_result:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "continue_failed"

        result = _parse_poll_json(ctx.poll_result.strip())
        ctx.poll_result = ""
        ctx.pending_agent = ""
        if result == "ok":
            _handle_agent_success(ctx)
            ctx.conflicting_task_id = ""
            return "ok"
        if result == "conflict":
            # The cascade legitimately hit another conflict further up the stack — not a
            # failure of this script, so resolving_conflict re-derives the *new* conflicting
            # branch fresh from scratch.
            _handle_agent_success(ctx)
            return "conflict"
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "continue_failed"


class CleaningUpStep(Step):
    """Removes this monitor's own dedicated worktree/branch once every task in the target set
    has merged — only when this monitor bootstrapped its own worktree (`ctx.own_worktree`); the
    `/watch-stack` in-session path never allocated one of its own to clean up. An inline step —
    simple, no-judgment git plumbing done natively rather than round-tripped through a script
    dispatch. Never reports `"cleaned"` on a failed removal — a failed cleanup must never be
    reported as a clean halt."""

    handles = "cleaning_up"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        return []

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.own_worktree:
            return "cleaned"

        try:
            common_dir = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            main_checkout = Path(common_dir).parent
            subprocess.run(
                ["git", "worktree", "remove", ctx.watch_worktree_path, "--force"],
                cwd=main_checkout, check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "branch", "-D", ctx.watch_worktree_branch],
                cwd=main_checkout, check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "cleanup_failed"

        _handle_agent_success(ctx)
        return "cleaned"


# ---------------------------------------------------------------------------
# PR-mode steps
# ---------------------------------------------------------------------------

class PrPollStep(Step):
    """PR mode's poll loop over `pr_list_poll.py` — no `gh stack` involvement at all, so no
    separate sync phase exists (unlike stack mode's `syncing_stack`/`scanning_stack_events`
    split)."""

    handles = "polling_pr"
    _PENDING_KEY = "polling_pr"

    def __init__(self, ctx: "PipelineContext", context_path: Path, log_dir: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path
        self._log_dir = log_dir

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if ctx.poll_result:
            return []
        script = Path(__file__).parent / "pr_list_poll.py"
        command = f'{sys.executable} "{script}" "{ctx.pr_numbers}"'
        log_path = _new_log_path(self._log_dir, ctx.work_item_id, "poll")
        return [{
            "action": "run_script",
            "message": f"Polling PRs {ctx.pr_numbers} for review comments, CI failures, and merges.",
            "command": command,
            "log_file": str(log_path),
            "write_section": "Poll Result",
            "result_format": '"no_change" | "all_complete" | {"task_work_item_id","event"}',
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        if not ctx.poll_result:
            _handle_agent_failure(ctx)
            _check_and_trigger_troubleshooter(
                "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
                ctx.consecutive_failures, ctx, self._context_path,
            )
            return "poll_failed"

        result = _parse_poll_json(ctx.poll_result.strip())
        ctx.poll_result = ""
        ctx.pending_agent = ""
        if result == "no_change":
            _handle_agent_success(ctx)
            return "no_change"
        if result == "all_complete":
            _handle_agent_success(ctx)
            return "all_complete"
        if isinstance(result, dict) and "task_work_item_id" in result and "event" in result:
            _handle_agent_success(ctx)
            ctx.poll_event_task_id = result["task_work_item_id"]
            return result["event"]
        _handle_agent_failure(ctx)
        _check_and_trigger_troubleshooter(
            "consecutive_failures", CONSECUTIVE_FAILURES_THRESHOLD,
            ctx.consecutive_failures, ctx, self._context_path,
        )
        return "poll_failed"


# ---------------------------------------------------------------------------
# Shared steps (both stack and PR mode)
# ---------------------------------------------------------------------------

class ReactStep(Step):
    """Reacts to a review comment or CI failure by spawning `fix-pr` (via the developer agent)
    against the *affected task's own* context file — never this monitor's own. Shared verbatim
    between stack mode and PR mode; both poll steps set `ctx.poll_event_task_id` identically.

    No failure branch is needed here: a failed spawn is caught by workflow-orchestrate's own
    generic dispatch-result check before this method is ever reached — matching current
    monitor-prs prose's own "do not retry automatically" convention exactly, just enforced by the
    engine instead of restated here."""

    handles = "reacting_fix"
    _PENDING_KEY = "reacting_fix"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if not ctx.poll_event_task_id or ctx.pending_agent == "reacting_fix":
            return []
        task_id = ctx.poll_event_task_id
        task_context_path = _task_context_path(task_id)
        section = f"Post-Handoff Fix {ctx.post_handoff_fix_count + 1}"
        return [{
            "action": "spawn_agent",
            "message": f"Reacting to a review comment or CI failure for {task_id}.",
            "agent": "dev-team:developer",
            "skill": "fix-pr",
            "args": task_id,
            "context_file": str(task_context_path),
            "read_sections": [],
            "write_section": section,
            "result_format": "successful",
        }]

    def handle_results(self) -> str:
        ctx = self._ctx
        task_id = ctx.poll_event_task_id
        task_context_path = _task_context_path(task_id)
        # Required fix (see plan Context): nothing else ever re-invokes the pipeline for this
        # task's own work_item_id to merge its scratch deliverable.
        merge_pending_deliverables(task_context_path, task_id)
        ctx.post_handoff_fix_count += 1
        ctx.poll_event_task_id = ""
        ctx.pending_agent = ""
        return "reacted"


class NotifyStep(Step):
    """Reacts to a human-authored PR comment by notifying the user directly — never spawns
    `fix-pr` for this event, since a human comment deserves a personal response, not a bot edit.
    Uses the new `"notify"` action verb (fire-and-forget, no write-back), so `pending_agent`
    gating is required here even though there's no agent spawn: nothing else signals "already
    notified" back into the context file the way a spawn's own written deliverable would."""

    handles = "notifying"
    _PENDING_KEY = "notifying"

    def __init__(self, ctx: "PipelineContext", context_path: Path) -> None:
        self._ctx = ctx
        self._context_path = context_path

    def get_actions(self) -> list[dict]:
        ctx = self._ctx
        if not ctx.poll_event_task_id or ctx.pending_agent == "notifying":
            return []
        task_id = ctx.poll_event_task_id
        task_ctx = _load_task_context(task_id)
        pr_url = task_ctx.pr_url if task_ctx else ""
        message = f"Human comment on {task_id}'s PR needs a response: {pr_url}"
        return [{"action": "notify", "message": message}]

    def handle_results(self) -> str:
        ctx = self._ctx
        ctx.poll_event_task_id = ""
        ctx.pending_agent = ""
        return "notified"


# ---------------------------------------------------------------------------
# step_handlers factory
# ---------------------------------------------------------------------------

def _build_step_handlers(
    ctx: "PipelineContext", context_path: Path, log_dir: Path,
) -> dict[str, Step]:
    return {
        "bootstrapping": BootstrappingStep(ctx, context_path, log_dir),
        "syncing_stack": SyncingStackStep(ctx, context_path, log_dir),
        "scanning_stack_events": ScanningStackEventsStep(ctx, context_path, log_dir),
        "resolving_conflict": ResolvingConflictStep(ctx, context_path),
        "continuing_rebase": ContinuingRebaseStep(ctx, context_path, log_dir),
        "cleaning_up": CleaningUpStep(ctx, context_path),
        "polling_pr": PrPollStep(ctx, context_path, log_dir),
        "reacting_fix": ReactStep(ctx, context_path),
        "notifying": NotifyStep(ctx, context_path),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="monitor_prs.py",
        description="long-lived PR monitor pipeline step machine",
    )
    parser.add_argument("work_item_id", metavar="work-item-id",
                        help="Epic id (stack mode) or synthetic watch-pr-<...> key (PR mode)")
    parser.add_argument("--workflow", metavar="path", default=None,
                        help="Path to a Mermaid stateDiagram-v2 workflow file")
    parser.add_argument("--plugin-root", metavar="path", default=None,
                        help="Plugin installation root (agents/ and commands/ resolved here)")
    parser.add_argument("--context-file", metavar="path", default=None,
                        help="Path to the pipeline context file (computed by get_context_path.py)")
    parser.add_argument("--print-context-path", metavar="repo-slug", default=None,
                        help="Print the context file path for the given repo slug and exit")
    args = parser.parse_args()

    if args.print_context_path is not None:
        print(dev_team.compute_context_path(args.work_item_id, args.print_context_path), flush=True)
        sys.exit(0)

    if not args.workflow:
        parser.error("--workflow is required")
    if not args.context_file:
        parser.error("--context-file is required")

    work_item_id = args.work_item_id
    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = REPO_ROOT / workflow_path

    context_path = Path(args.context_file)
    log_dir = context_path.parent / "logs"

    dev_team.run_pipeline(
        work_item_id,
        workflow_path,
        context_path,
        step_handlers_factory=lambda ctx, cp: _build_step_handlers(ctx, cp, log_dir),
    )


if __name__ == "__main__":
    main()
