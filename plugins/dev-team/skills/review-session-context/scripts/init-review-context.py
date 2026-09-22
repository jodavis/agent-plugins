#!/usr/bin/env python3
"""Initialise the review-session context file at a given path.

Usage: init-review-context.py <review-context-file>

Creates the file with the documented blank frontmatter fields and the reserved-section
documentation if it does not already exist. Creates parent directories as needed.
Idempotent: a second run against an existing file is a no-op. Exits non-zero on error.

Unlike use-context-file's init-context-file.py, this file carries no embedded "Project
Configuration" section and needs no work-item-id/timestamp substitution -- every
frontmatter field here (repo_scope, isolation_kind, owner, repo, pr_number, pr_url,
worktree_path, head_ref, guide_path, work_item_id) is set later, by whichever component
resolves it, via the same "Updating frontmatter fields" Edit convention documented in
this skill's SKILL.md.
"""

import sys
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).parent.parent / "assets" / "review_context_template.md"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: init-review-context.py <review-context-file>", file=sys.stderr)
        sys.exit(1)

    context_path = Path(sys.argv[1]).expanduser()

    if context_path.exists():
        return

    try:
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
        context_path.parent.mkdir(parents=True, exist_ok=True)
        context_path.write_text(template, encoding="utf-8")
    except OSError as e:
        print(f"Error: could not initialize review context file at {context_path}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
