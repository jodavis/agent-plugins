"""Bounded polling loop over pr_event_detector.detect_pr_events().

Loops the PR event detector on a fixed interval, self-bounded to under Bash's 10-minute timeout
cap; exits early with whichever condition(s) fired, or "no_change" at the window's end.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from pr_event_detector import detect_pr_events  # noqa: E402


def poll(
    task_work_item_id: str,
    max_seconds: int = 480,
    sleep=time.sleep,
    clock=time.monotonic,
) -> list[str] | Literal["no_change"]:
    start = clock()
    while True:
        events = detect_pr_events(task_work_item_id)
        if events:
            return events
        if clock() - start >= max_seconds:
            return "no_change"
        sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_work_item_id")
    parser.add_argument("max_seconds", nargs="?", type=int, default=480)
    args = parser.parse_args()

    try:
        result = poll(args.task_work_item_id, args.max_seconds)
    except Exception as e:
        print(f"Error: could not poll PR events for '{args.task_work_item_id}': {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
