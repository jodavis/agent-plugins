#!/usr/bin/env python3
"""Compute the dev-team context file path for a work item.

Usage: compute-context-file.py <work-item-id>

Prints the absolute path to the context file on stdout.
Does NOT create the file — use init-context-file.py for that.
The path follows the same convention as dev_team.py:
  <DEV_TEAM_STATE_DIR or ~/.dev-team>/<repo-slug>/<work-item-id>.md
"""

import os
import re
import subprocess
import sys
from pathlib import Path


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
    print(context_path, flush=True)


if __name__ == "__main__":
    main()
