"""Bounded polling loop over `detect_next_stack_event.detect_next_stack_event()`, for
`monitor_prs.py`'s `scanning_stack_events` state.

Factored out of `stack_pr_poll.py`'s combined sync+scan loop so `ScanningStackEventsStep` can
dispatch and observe scanning independently of syncing (`SyncingStackStep`, in `stack_sync.py`)
— a poll cycle re-syncs (via a fresh `syncing_stack` dispatch) before every scan, so this script
never calls `gh stack sync` itself. Reuses `stack_pr_poll._stack_complete()` rather than
duplicating it.

Nothing firing loops on a fixed interval until max_seconds elapses, at which point "no_change" is
returned — mirrors `stack_pr_poll.py`'s own injectable-sleep/clock shape exactly.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT  # noqa: E402
from detect_next_stack_event import detect_next_stack_event  # noqa: E402
from stack_pr_poll import _stack_complete  # noqa: E402


def scan(
    max_seconds: int = 480,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Literal["stack_complete", "no_change"] | dict:
    start = clock()
    while True:
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
        result = scan(args.max_seconds)
    except Exception as e:
        print(f"Error: could not scan stack events: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
