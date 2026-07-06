#!/usr/bin/env python3
"""Derive and create the dev-team todo log path.

Usage: get_todo_log_path.py <context_file> <work-item-id>

Prints the todo log path, creating its parent directory and the (empty) file
if they do not already exist.
"""

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: {Path(sys.argv[0]).name} <context_file> <work-item-id>", file=sys.stderr)
        sys.exit(1)

    context_file = Path(sys.argv[1])
    work_item_id = sys.argv[2]

    todo_log = context_file.parent / "logs" / f"{work_item_id}-todo.log"
    todo_log.parent.mkdir(parents=True, exist_ok=True)
    todo_log.touch(exist_ok=True)

    print(todo_log, flush=True)


if __name__ == "__main__":
    main()
