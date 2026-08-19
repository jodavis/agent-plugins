"""PR event detector.

Given a task's context file and its PR's current GitHub/git state, determines which of the three
monitor conditions (review_comment, ci_failure, task_merged) have newly fired. base_updated and
dependency_merged have been retired — they are subsumed by `gh stack sync` — see
detect_next_stack_event.py.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402

_PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")


def _pr_state_and_base(pr_url: str) -> tuple[str, str]:
    result = subprocess.run(
        ["gh", "pr", "view", pr_url, "--json", "state,baseRefName"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "", ""
    return data.get("state", ""), data.get("baseRefName", "")


def _parse_pr_url(pr_url: str) -> tuple[str, str, str]:
    match = _PR_URL_RE.match(pr_url)
    if not match:
        raise ValueError(f"pr_url does not match expected GitHub PR URL format: {pr_url!r}")
    return match.groups()


def _review_comment_and_ci_events(ctx: PipelineContext) -> list[Literal["review_comment", "ci_failure"]]:
    events: list[str] = []

    # 1. review_comment
    owner, repo, number = _parse_pr_url(ctx.pr_url)
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}/comments"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        comments = json.loads(result.stdout)
    except json.JSONDecodeError:
        comments = []
    if comments:
        max_id = max(c["id"] for c in comments)
        last_seen = int(ctx.extra_frontmatter.get("last_seen_review_comment_id") or 0)
        if max_id > last_seen:
            events.append("review_comment")
            ctx.extra_frontmatter["last_seen_review_comment_id"] = str(max_id)

    # 2. ci_failure
    checks_result = subprocess.run(
        ["gh", "pr", "checks", ctx.pr_url, "--json", "bucket"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        checks = json.loads(checks_result.stdout)
    except json.JSONDecodeError:
        checks = []
    buckets = [c.get("bucket") for c in checks]
    if any(b in ("fail", "cancel") for b in buckets):
        conclusion = "failing"
    elif any(b == "pending" for b in buckets):
        conclusion = "pending"
    elif buckets:
        conclusion = "passing"
    else:
        conclusion = ""
    if conclusion == "failing" and conclusion != ctx.extra_frontmatter.get("last_seen_ci_conclusion", ""):
        events.append("ci_failure")
        ctx.extra_frontmatter["last_seen_ci_conclusion"] = "failing"

    return events


def detect_pr_events(
    task_work_item_id: str,
) -> list[Literal["review_comment", "ci_failure", "task_merged"]]:
    path = compute_context_path(task_work_item_id, get_repo_slug())
    if not path.exists():
        return []
    ctx = PipelineContext.load(path)
    if not ctx.pr_url:
        return []

    events = _review_comment_and_ci_events(ctx)
    changed = bool(events)

    # 3. task_merged
    own_state, _ = _pr_state_and_base(ctx.pr_url)
    if own_state == "MERGED":
        events.append("task_merged")

    if changed:
        ctx.save(path)

    return events
