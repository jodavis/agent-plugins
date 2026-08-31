"""Bounded polling loop over a fixed, explicit list of PR numbers — the "PR mode" counterpart to
stack_pr_poll.py's whole-stack polling, for monitoring one or more PRs that aren't part of (or
aren't known to be part of) a `gh stack`. No `gh stack` involvement at all: no sync, no
rebase-cascade handling — an arbitrary PR list has no cross-branch cascade to reconcile.

Each PR number is resolved to its own task_work_item_id from its head branch's last path segment
(mirroring detect_next_stack_event.py's own convention), then checked via
pr_event_detector.detect_pr_events() — the same per-task primitive `stack_pr_poll.py` relies on
indirectly through detect_next_stack_event.py. The first task with a fired
review_comment/human_comment/ci_failure event checks out its own branch and is returned
immediately as {"task_work_item_id", "event"}; a task_merged event drops that PR from the active
set silently. Once every given PR has merged, returns "all_complete". Nothing firing loops on a
fixed interval until max_seconds elapses, at which point "no_change" is returned — mirrors
stack_pr_poll.py's own injectable-sleep/clock shape exactly.
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
from detect_next_stack_event import _WORK_ITEM_ID_RE  # noqa: E402
from pr_event_detector import detect_pr_events  # noqa: E402


def _head_ref(pr_number: int, cwd: Path) -> str:
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "headRefName"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    return data.get("headRefName", "")


def _task_work_item_id(head_ref: str) -> str:
    last_segment = head_ref.rsplit("/", 1)[-1]
    match = _WORK_ITEM_ID_RE.match(last_segment)
    return match.group(0) if match else last_segment


def poll(
    pr_numbers: list[int],
    max_seconds: int = 480,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Literal["all_complete", "no_change"] | dict:
    start = clock()
    active = list(pr_numbers)
    while True:
        still_active = []
        for pr_number in active:
            head_ref = _head_ref(pr_number, REPO_ROOT)
            if not head_ref:
                # Transient lookup failure (or a closed/unmerged PR gh can't resolve right now) —
                # keep it active and retry next iteration rather than dropping it silently.
                still_active.append(pr_number)
                continue

            task_work_item_id = _task_work_item_id(head_ref)
            events = detect_pr_events(task_work_item_id)
            if "task_merged" in events:
                continue  # done monitoring this one

            still_active.append(pr_number)
            fired = [e for e in events if e != "task_merged"]
            if fired:
                subprocess.run(
                    ["git", "checkout", head_ref],
                    cwd=REPO_ROOT,
                    timeout=30,
                    check=True,
                )
                return {"task_work_item_id": task_work_item_id, "event": fired[0]}

        active = still_active
        if not active:
            return "all_complete"

        if clock() - start >= max_seconds:
            return "no_change"
        sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_numbers", help="Comma-separated PR numbers to monitor")
    parser.add_argument("max_seconds", nargs="?", type=int, default=480)
    args = parser.parse_args()

    try:
        pr_numbers = [int(n) for n in args.pr_numbers.split(",") if n.strip()]
    except ValueError as e:
        print(f"Error: could not parse PR numbers: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = poll(pr_numbers, args.max_seconds)
    except Exception as e:
        print(f"Error: could not poll PR events: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
