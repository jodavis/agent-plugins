#!/usr/bin/env python3
"""Task readiness checker.

Reports per-dependency PR/merge status and whether a task-work-item is
eligible to start given its declared dependencies.

Usage: task_readiness.py <task-work-item-id> [comma-separated dependency ids]

A task is eligible once every declared dependency has reached "done" — fully signed off *and*
linked into the epic's `gh stack` via `add-to-pr-stack`. This is stricter than ADR-374's original
"ready (PR created) or done" rule: since registration into the stack no longer happens eagerly at
a task's own start (`ensure-working-branch` never touches `gh stack` at all — see
`stack_registration.py`), an open PR no longer implies a dependency is actually in the stack, so
"ready" alone is no longer sufficient — a dependent must wait for its dependencies to be fully
`done` before `ensure-working-branch`'s own dependency-anchor logic can rely on their branches
being complete and their PRs already linked. No dependency ever needs to actually *merge*, though
— "done" stops well short of that.

`main()` is a thin CLI wrapper so a prose skill can invoke this via `Bash`: it prints
`is_task_eligible`'s result as `{"status": ..., "base_branch": null}` JSON to stdout on
success, or a clear `Error: ...` message to stderr with a non-zero exit on failure. `base_branch`
is kept as an unconditional `null` in this printed shape for backward compatibility with any
external caller of this CLI form — `is_task_eligible` itself has never returned a `base_branch`
since ADR-374; no current skill invokes this CLI form via `Bash` (callers use the Python API
directly, e.g. `concurrent_schedule.py`).
"""

import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402


def dependency_status_and_context(
    task_work_item_id: str,
) -> tuple[Literal["ready", "in_progress", "done", "failed", "not_started"], PipelineContext | None]:
    """Load a task's context file once and derive both its coarse status and the loaded
    `PipelineContext` (or `None` if it has no context file yet), so callers that need both don't
    re-derive `get_repo_slug()`/reload the context file a second time. Public (not
    underscore-prefixed) because `concurrent_schedule.py`'s `compute_next_batch()` also reuses
    this same read to avoid a second, independent context-file read when building its `running`
    snapshot for a task whose status it already computed."""
    path = compute_context_path(task_work_item_id, get_repo_slug())
    if not path.exists():
        return ("not_started", None)
    ctx = PipelineContext.load(path)
    if ctx.state == "done":
        return ("done", ctx)
    if ctx.state == "failed":
        return ("failed", ctx)
    if ctx.pr_url:
        return ("ready", ctx)
    return ("in_progress", ctx)


def dependency_status(task_work_item_id: str) -> Literal["ready", "in_progress", "done", "failed", "not_started"]:
    status, _ = dependency_status_and_context(task_work_item_id)
    return status


def snapshot_from_status_and_context(
    status: Literal["ready", "in_progress", "done", "failed", "not_started"],
    ctx: PipelineContext | None,
) -> dict:
    """Build the `{"status", "last_updated", "worktree_path"}` snapshot dict from an
    already-loaded `(status, ctx)` pair — the shared body behind `task_snapshot()`, factored out
    so a caller that already holds both (e.g. `dependency_status_and_context()`'s own result) can
    reuse them without a second context-file read."""
    if ctx is None:
        return {"status": status, "last_updated": None, "worktree_path": None}
    return {
        "status": status,
        "last_updated": ctx.last_updated.isoformat(),
        "worktree_path": ctx.extra_frontmatter.get("worktree_path"),
    }


def task_snapshot(task_work_item_id: str) -> dict:
    status, ctx = dependency_status_and_context(task_work_item_id)
    return snapshot_from_status_and_context(status, ctx)


def is_task_eligible(task_work_item_id: str, dependency_ids: list[str]) -> Literal["eligible", "waiting", "blocked"]:
    """A task is eligible once every declared dependency has reached "done" — fully signed off
    and linked into the epic's `gh stack` via `add-to-pr-stack`. An open PR alone ("ready") is no
    longer sufficient: unlike the old eager-registration design, a "ready" dependency isn't
    necessarily in the stack yet, so `ensure-working-branch`'s dependency-anchor logic couldn't
    safely base this task's branch on it. No dependency ever needs to actually *merge*, though —
    "done" stops well short of that. "blocked" if any dependency reached the `failed` terminal
    state, regardless of the others. "waiting" while any dependency is still short of "done" and
    none have failed."""
    if not dependency_ids:
        return "eligible"
    statuses = {dep_id: dependency_status(dep_id) for dep_id in dependency_ids}
    if "failed" in statuses.values():
        return "blocked"
    if all(status == "done" for status in statuses.values()):
        return "eligible"
    return "waiting"


def main() -> None:
    if len(sys.argv) < 2:
        print(
            f"Usage: {Path(sys.argv[0]).name} <task-work-item-id> [comma-separated dependency ids]",
            file=sys.stderr,
        )
        sys.exit(1)

    task_work_item_id = sys.argv[1]
    raw_dependencies = sys.argv[2] if len(sys.argv) > 2 else ""
    dependency_ids = [dep.strip() for dep in raw_dependencies.split(",") if dep.strip()]

    try:
        status = is_task_eligible(task_work_item_id, dependency_ids)
    except Exception as e:
        print(f"Error: could not compute task eligibility for '{task_work_item_id}': {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"status": status, "base_branch": None}), flush=True)


if __name__ == "__main__":
    main()
