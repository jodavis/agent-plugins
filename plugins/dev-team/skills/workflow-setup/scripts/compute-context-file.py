#!/usr/bin/env python3
"""Compute and initialise the dev-team context file for a work item.

Usage: compute-context-file.py <work-item-id>

Prints the absolute path to the context file on stdout.
Creates the file with default frontmatter if it does not already exist.
The path follows the same convention as dev_team.py:
  <DEV_TEAM_STATE_DIR or ~/.dev-team>/<repo-slug>/<work-item-id>.md
"""

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

# Context file template from the assets directory
_TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "context_template.md"

def get_repo_slug() -> str:
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: could not read git remote 'origin': {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Strip protocol/host prefix and .git suffix from any of these forms:
    #   https://github.com/org/repo.git
    #   https://github.com/org/repo
    #   git@github.com:org/repo.git
    #   git@github.com:org/repo
    slug = re.sub(r"^https?://[^/]+/", "", url)
    slug = re.sub(r"^[^@]+@[^:]+:", "", slug)
    slug = re.sub(r"\.git$", "", slug)

    if not slug:
        print(f"Error: could not extract repo slug from remote URL: {url}", file=sys.stderr)
        sys.exit(1)
    return slug


def compute_context_path(work_item_id: str) -> Path:
    base_env = os.environ.get("DEV_TEAM_STATE_DIR")
    base = Path(base_env) if base_env else Path.home() / ".dev-team"
    repo_slug = get_repo_slug()
    return base / repo_slug / f"{work_item_id}.md"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: compute-context-file.py <work-item-id>", file=sys.stderr)
        sys.exit(1)

    work_item_id = sys.argv[1]
    context_path = compute_context_path(work_item_id)

    if not context_path.exists():
        context_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().isoformat()
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
        content = template.format(work_item_id=work_item_id, timestamp=timestamp)
        context_path.write_text(content, encoding="utf-8")

    print(context_path, flush=True)


if __name__ == "__main__":
    main()
