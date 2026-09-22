#!/usr/bin/env python3
"""Compute the review-session context file path for a worktree/clone root.

Usage: compute-review-context.py <worktree-or-clone-root>

Prints the absolute path to .dev-team-review.md under the given root on stdout.
Does NOT create the file -- use init-review-context.py for that.

Unlike use-context-file's compute-context-file.py, this file lives inside the review
worktree/clone itself, not outside the repo -- there is no repo-slug or
~/.dev-team/DEV_TEAM_STATE_DIR involvement, since the root is already the isolated
working copy for this review session.
"""

import sys
from pathlib import Path


def compute_review_context_path(root: str) -> Path:
    return Path(root).expanduser().resolve() / ".dev-team-review.md"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: compute-review-context.py <worktree-or-clone-root>", file=sys.stderr)
        sys.exit(1)

    root = sys.argv[1]
    context_path = compute_review_context_path(root)
    print(context_path, flush=True)


if __name__ == "__main__":
    main()
