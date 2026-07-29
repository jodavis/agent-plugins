#!/usr/bin/env python3
"""Task readiness checker.

Reports per-dependency PR/merge status and whether a task-work-item is
eligible to start given its declared dependencies.

Usage: task_readiness.py <task-work-item-id> [comma-separated dependency ids]

`main()` is a thin CLI wrapper so a prose skill (`ensure-working-branch`, which has no other
way to call a Python function directly) can invoke this via `Bash`: it prints
`is_task_eligible`'s result as `{"status": ..., "base_branch": ...}` JSON to stdout on success,
or a clear `Error: ...` message to stderr with a non-zero exit on failure.
"""

import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402


def _dependency_status_and_context(
    task_work_item_id: str,
) -> tuple[Literal["ready", "in_progress", "done", "failed", "not_started"], PipelineContext | None]:
    """Load a dependency's context file once and derive both its coarse status and the loaded
    `PipelineContext` (or `None` if it has no context file yet), so callers that need both don't
    re-derive `get_repo_slug()`/reload the context file a second time."""
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
    status, _ = _dependency_status_and_context(task_work_item_id)
    return status


def task_snapshot(task_work_item_id: str) -> dict:
    status, ctx = _dependency_status_and_context(task_work_item_id)
    if ctx is None:
        return {"status": status, "last_updated": None, "worktree_path": None}
    return {
        "status": status,
        "last_updated": ctx.last_updated.isoformat(),
        "worktree_path": ctx.extra_frontmatter.get("worktree_path"),
    }


def is_task_eligible(task_work_item_id: str, dependency_ids: list[str]) -> tuple[Literal["eligible", "waiting", "blocked"], str | None]:
    if not dependency_ids:
        return ("eligible", None)
    results = {dep_id: _dependency_status_and_context(dep_id) for dep_id in dependency_ids}
    statuses = {dep_id: status for dep_id, (status, _) in results.items()}
    if "failed" in statuses.values():
        return ("blocked", None)
    not_done = [dep_id for dep_id, status in statuses.items() if status != "done"]
    if not not_done:
        return ("eligible", None)
    if len(not_done) == 1 and statuses[not_done[0]] == "ready":
        _, ctx = results[not_done[0]]
        branch = ctx.extra_frontmatter.get("working_branch")
        return ("eligible", branch)
    return ("waiting", None)


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
        status, base_branch = is_task_eligible(task_work_item_id, dependency_ids)
    except Exception as e:
        print(f"Error: could not compute task eligibility for '{task_work_item_id}': {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"status": status, "base_branch": base_branch}), flush=True)


if __name__ == "__main__":
    main()
