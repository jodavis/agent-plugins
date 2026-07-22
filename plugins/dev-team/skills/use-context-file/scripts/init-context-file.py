#!/usr/bin/env python3
"""Initialise the dev-team context file at a given path.

Usage: init-context-file.py <work-item-id> <context-file>

Creates the file with default frontmatter if it does not already exist, with the
merged project configuration embedded as its first section — computed once here so
callers never need to invoke get-project-configuration themselves for a context file
that already has one. Creates parent directories as needed. Exits non-zero on error.

The embedded section uses the same `<!-- section:Project Configuration -->` sentinel
and plain-JSON body that dev_team.py's PipelineContext reads and writes, so a context
file is interchangeable regardless of which of the two ever creates it first.
"""

import datetime
import json
import sys
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "context_template.md"
_MERGE_CONFIG_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "get-project-configuration" / "scripts"
)

sys.path.insert(0, str(_MERGE_CONFIG_SCRIPTS_DIR))
from merge_config import YamlParseError, build_merged_config  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: init-context-file.py <work-item-id> <context-file>", file=sys.stderr)
        sys.exit(1)

    work_item_id = sys.argv[1]
    context_path = Path(sys.argv[2]).expanduser()

    if context_path.exists():
        return

    try:
        config = build_merged_config()
    except (YamlParseError, RuntimeError) as e:
        print(f"Error: could not compute project configuration: {e}", file=sys.stderr)
        sys.exit(1)

    context_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().isoformat()
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    content = template.format(work_item_id=work_item_id, timestamp=timestamp)
    content += (
        "\n<!-- section:Project Configuration -->\n\n"
        f"{json.dumps(config, indent=2)}\n"
    )
    context_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
