"""PR event detector.

Given a task's context file and its PR's current GitHub/git state, determines which of the five
monitor conditions (review_comment, ci_failure, base_updated, dependency_merged, task_merged)
have newly fired.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
import task_dependencies  # noqa: E402
from dev_team import REPO_ROOT, compute_context_path  # noqa: E402
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
    data = json.loads(result.stdout)
    return data.get("state", ""), data.get("baseRefName", "")


def _remote_tip_sha(branch: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", "origin", branch],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    first_line = (result.stdout or "").splitlines()[:1]
    return first_line[0].split()[0] if first_line and first_line[0].split() else ""


def detect_pr_events(
    task_work_item_id: str,
) -> list[Literal["review_comment", "ci_failure", "base_updated", "dependency_merged", "task_merged"]]:
    path = compute_context_path(task_work_item_id, get_repo_slug())
    if not path.exists():
        return []
    ctx = PipelineContext.load(path)
    if not ctx.pr_url:
        return []

    events: list[str] = []
    changed = False

    owner, repo, number = _PR_URL_RE.match(ctx.pr_url).groups()
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}/comments"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    comments = json.loads(result.stdout)
    if comments:
        max_id = max(c["id"] for c in comments)
        last_seen = int(ctx.extra_frontmatter.get("last_seen_review_comment_id") or 0)
        if max_id > last_seen:
            events.append("review_comment")
            ctx.extra_frontmatter["last_seen_review_comment_id"] = str(max_id)
            changed = True

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
        changed = True

    # 3. base_updated
    base_branch = ctx.extra_frontmatter.get("base_branch", "")
    if base_branch:
        current_sha = _remote_tip_sha(base_branch)
        if current_sha:
            stored_sha = ctx.extra_frontmatter.get("base_branch_sha", "")
            if not stored_sha:
                ctx.extra_frontmatter["base_branch_sha"] = current_sha
                changed = True
            elif current_sha != stored_sha:
                events.append("base_updated")
                ctx.extra_frontmatter["base_branch_sha"] = current_sha
                changed = True

    # 4. dependency_merged
    if ctx.spec_path:
        spec_file = REPO_ROOT / ctx.spec_path
        if spec_file.exists():
            try:
                graph = task_dependencies.parse_task_dependencies(spec_file.read_text())
            except task_dependencies.TaskDependencyError:
                graph = {}
            for dep_id in graph.get(task_work_item_id, []):
                dep_path = compute_context_path(dep_id, get_repo_slug())
                if not dep_path.exists():
                    continue
                dep_ctx = PipelineContext.load(dep_path)
                if not dep_ctx.pr_url:
                    continue
                dep_state, dep_base = _pr_state_and_base(dep_ctx.pr_url)
                if dep_state != "MERGED":
                    continue
                if dep_base and dep_base != ctx.extra_frontmatter.get("base_branch", ""):
                    events.append("dependency_merged")
                    ctx.extra_frontmatter["base_branch"] = dep_base
                    changed = True
                    sha = _remote_tip_sha(dep_base)
                    if sha:
                        ctx.extra_frontmatter["base_branch_sha"] = sha
                    break

    # 5. task_merged
    own_state, _ = _pr_state_and_base(ctx.pr_url)
    if own_state == "MERGED":
        events.append("task_merged")

    if changed:
        ctx.save(path)

    return events
