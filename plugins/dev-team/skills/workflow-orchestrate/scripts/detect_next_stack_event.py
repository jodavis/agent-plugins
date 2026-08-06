"""Stack PR event detector.

`detect_next_stack_event(epic_id)` scans a stack's branches (via `gh_stack.view()`, already in
stack-position order) and returns the first actionable event across the whole stack — one of
review_comment, ci_failure, or task_merged — or `None` if nothing fired this call.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT, compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402
from pr_event_detector import _review_comment_and_ci_events  # noqa: E402

_STACKED_PRS_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "work-with-stacked-prs" / "scripts"
)
sys.path.insert(0, str(_STACKED_PRS_SCRIPTS))
import gh_stack  # noqa: E402


def detect_next_stack_event(epic_id: str) -> dict | None:
    """`epic_id` is unused — `gh_stack.view()`/`sync()` operate on whatever stack is anchored in
    the current worktree (no epic-scoped filter exists in `gh_stack.py`); the caller is
    responsible for running from the correct worktree."""
    status, detail = gh_stack.view(cwd=REPO_ROOT)
    if status == "error":
        return None

    for branch in detail.get("branches", []):
        name = branch.get("name", "")
        task_work_item_id = name.rsplit("/", 1)[-1]
        if not task_work_item_id:
            continue

        path = compute_context_path(task_work_item_id, get_repo_slug())
        if not path.exists():
            continue
        ctx = PipelineContext.load(path)

        if branch.get("isMerged"):
            if ctx.extra_frontmatter.get("stack_task_merged_seen") == "true":
                continue
            ctx.extra_frontmatter["stack_task_merged_seen"] = "true"
            ctx.save(path)
            return {"type": "task_merged", "task_work_item_id": task_work_item_id}

        if not ctx.pr_url:
            continue

        events = _review_comment_and_ci_events(ctx)
        if events:
            subprocess.run(
                ["git", "checkout", name],
                cwd=REPO_ROOT,
                timeout=30,
                check=True,
            )
            ctx.save(path)
            return {"type": events[0], "task_work_item_id": task_work_item_id}

    return None
