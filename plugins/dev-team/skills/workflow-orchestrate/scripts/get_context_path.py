#!/usr/bin/env python3
"""Deterministically resolve the dev-team context file path.

Usage: get_context_path.py <work-item-id>

Derives the repo slug from `git remote get-url origin`, then delegates to
dev_team.compute_context_path() to compute the canonical state-file path.
Exits non-zero and prints a clear message to stderr on failure.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import compute_context_path  # noqa: E402


def get_repo_slug() -> str:
    # GIT_REMOTE_URL_OVERRIDE is a test seam; it is never set in production.
    override = os.environ.get("GIT_REMOTE_URL_OVERRIDE")
    if override is not None:
        url = override
    else:
        try:
            url = subprocess.check_output(
                ["git", "remote", "get-url", "origin"],
                text=True,
                stderr=subprocess.PIPE,
            ).strip()
        except subprocess.CalledProcessError as e:
            print(f"Error: could not read git remote 'origin': {e.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    # Extract org/repo, handling four common URL forms:
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


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {Path(sys.argv[0]).name} <work-item-id>", file=sys.stderr)
        sys.exit(1)

    work_item_id = sys.argv[1]
    repo_slug = get_repo_slug()
    print(compute_context_path(work_item_id, repo_slug), flush=True)


if __name__ == "__main__":
    main()
