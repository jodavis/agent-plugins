#!/usr/bin/env python3
"""Append a single todo-write JSON payload to the shared todo log.

Usage: append_todo_log.py <todo-log> < <todo-write-json>

Reads the JSON payload from stdin (avoiding shell quoting of embedded quotes
or apostrophes, which is unreliable via `echo '...'`), validates it, and
appends it as one line to <todo-log>. Always appends — never truncates or
rewrites the file, since other agents may be sharing it concurrently.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {Path(sys.argv[0]).name} <todo-log>", file=sys.stderr)
        sys.exit(1)

    todo_log = Path(sys.argv[1])
    payload = sys.stdin.read().strip()

    if not payload:
        print("Error: no JSON payload provided on stdin", file=sys.stderr)
        sys.exit(1)

    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"Error: stdin is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    todo_log.parent.mkdir(parents=True, exist_ok=True)
    with todo_log.open("a", encoding="utf-8") as f:
        f.write(payload + "\n")


if __name__ == "__main__":
    main()
