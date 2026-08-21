"""Stack PR event detector.

`detect_next_stack_event()` scans a stack's branches (via `gh_stack.view()`, already in
stack-position order) and returns the first actionable event across the whole stack — one of
review_comment, human_comment, ci_failure, or task_merged — or `None` if nothing fired this call.
Operates on whatever stack is anchored in the current worktree (no feature-scoped filter exists in
`gh_stack.py`); the caller is responsible for running from the correct worktree.
"""

import re
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

# Matches the `<task-work-item-id>` prefix of a branch's last path segment, which the
# `working-branches.task` config template (`dev/<user-alias>/<task-work-item-id>-<slug>`) may
# follow with an optional `-<slug>`. Falls back to the whole segment when it doesn't match, so
# non-standard id formats still work rather than being silently dropped.
_WORK_ITEM_ID_RE = re.compile(r"^[A-Za-z]+-\d+")


def detect_next_stack_event() -> dict | None:
    status, detail = gh_stack.view(cwd=REPO_ROOT)
    if status == "error":
        return None

    for branch in detail.get("branches", []):
        name = branch.get("name", "")
        last_segment = name.rsplit("/", 1)[-1]
        if not last_segment:
            continue
        match = _WORK_ITEM_ID_RE.match(last_segment)
        task_work_item_id = match.group(0) if match else last_segment

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
