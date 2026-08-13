"""Bounded polling loop over `gh stack sync` and
detect_next_stack_event.detect_next_stack_event().

Every iteration runs the `sync` operation first (silent on success); a genuine conflict — a
rebase left mid-flight by sync's own cascade-rebase step — returns "conflict" immediately,
without ever consulting the detector. On a clean sync, the Stack PR event detector decides what
happens next: a task_merged result is untracked silently and the loop continues unless every
branch in the stack is now merged ("stack_complete"); a review_comment/ci_failure result — the
detector has already checked out that task's branch — is returned immediately as
{"task_work_item_id", "event"}. Nothing firing loops on a fixed interval until max_seconds
elapses, at which point "no_change" is returned. Self-bounded to stay well under Bash's
10-minute timeout cap, mirroring watch_pr_poll.py's own injectable-sleep/clock shape exactly.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT  # noqa: E402
from detect_next_stack_event import detect_next_stack_event  # noqa: E402

_STACKED_PRS_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "work-with-stacked-prs" / "scripts"
)
sys.path.insert(0, str(_STACKED_PRS_SCRIPTS))
import gh_stack  # noqa: E402


def _rebase_in_progress(cwd: Path) -> bool:
    """Worktree-relative check for a mid-rebase git state left by `sync`'s cascade-rebase step,
    mirroring resolve-rebase-conflict/SKILL.md step 1's own check. Resolves the worktree's own
    git-dir via `git rev-parse --git-dir` first (ADR-370 finding #1: a worktree's rebase state
    lives under its own `.git/worktrees/<name>/`, not a fixed `.git/` path relative to some other
    worktree) rather than assuming `.git/` directly."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = Path(cwd) / git_dir
    return (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir()


def _stack_complete(cwd: Path) -> bool:
    """Every branch in the current stack is merged. The full stack's own `view()` membership
    stands in for the "target set" (see ADR-377's task brief, Known ambiguity #3) — no narrower,
    feature-scoped target-set source is available to a bare script."""
    status, detail = gh_stack.view(cwd=cwd)
    if status != "ok":
        return False
    branches = detail.get("branches", [])
    if not branches:
        return False
    return all(branch.get("isMerged") for branch in branches)


def poll(
    max_seconds: int = 480,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Literal["conflict", "stack_complete", "no_change"] | dict:
    start = clock()
    while True:
        gh_stack.sync(cwd=REPO_ROOT)
        if _rebase_in_progress(REPO_ROOT):
            return "conflict"

        event = detect_next_stack_event()
        if event is not None:
            if event["type"] == "task_merged":
                if _stack_complete(REPO_ROOT):
                    return "stack_complete"
            else:
                return {"task_work_item_id": event["task_work_item_id"], "event": event["type"]}

        if clock() - start >= max_seconds:
            return "no_change"
        sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("max_seconds", nargs="?", type=int, default=480)
    args = parser.parse_args()

    try:
        result = poll(args.max_seconds)
    except Exception as e:
        print(f"Error: could not poll stack events: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
