"""Task readiness checker.

Reports per-dependency PR/merge status and whether a task-work-item is
eligible to start given its declared dependencies.
"""

import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402


def dependency_status(task_work_item_id: str) -> Literal["ready", "in_progress", "done", "failed", "not_started"]:
    path = compute_context_path(task_work_item_id, get_repo_slug())
    if not path.exists():
        return "not_started"
    ctx = PipelineContext.load(path)
    if ctx.state == "done":
        return "done"
    if ctx.state == "failed":
        return "failed"
    if ctx.pr_url:
        return "ready"
    return "in_progress"


def is_task_eligible(task_work_item_id: str, dependency_ids: list[str]) -> tuple[Literal["eligible", "waiting", "blocked"], str | None]:
    if not dependency_ids:
        return ("eligible", None)
    statuses = {dep_id: dependency_status(dep_id) for dep_id in dependency_ids}
    if "failed" in statuses.values():
        return ("blocked", None)
    not_done = [dep_id for dep_id, status in statuses.items() if status != "done"]
    if not not_done:
        return ("eligible", None)
    if len(not_done) == 1 and statuses[not_done[0]] == "ready":
        path = compute_context_path(not_done[0], get_repo_slug())
        branch = PipelineContext.load(path).extra_frontmatter.get("working_branch")
        return ("eligible", branch)
    return ("waiting", None)
