#!/usr/bin/env python3
"""Initialise the dev-team context file at a given path.

Usage: init-context-file.py <work-item-id> <context-file>

Creates the file with default frontmatter if it does not already exist.
Creates parent directories as needed.
Exits non-zero on error.
"""

import datetime
import sys
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "context_template.md"


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: init-context-file.py <work-item-id> <context-file>", file=sys.stderr)
        sys.exit(1)

    work_item_id = sys.argv[1]
    context_path = Path(sys.argv[2]).expanduser()

    if context_path.exists():
        return

    context_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().isoformat()
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    content = template.format(work_item_id=work_item_id, timestamp=timestamp)
    context_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
