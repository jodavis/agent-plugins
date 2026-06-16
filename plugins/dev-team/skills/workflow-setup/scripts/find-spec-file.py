#!/usr/bin/env python3
"""Find the spec file for a work item and update the context file.

Usage: find-spec-file.py <work-item-id> <context-file>

Searches the repository for a _spec_*.md file whose text contains <work-item-id>.
On success:
  - Writes the repo-relative path into the spec_path frontmatter field of <context-file>
  - Prints the relative path to stdout
  - Exits 0

On failure (none found, or ambiguous):
  - Prints an error to stderr
  - Exits 1
"""

import os
import re
import sys
from pathlib import Path


def find_repo_root() -> Path:
    current = Path(os.getcwd()).resolve()
    while True:
        if (current / ".git").is_dir() or (current / ".claude").is_dir():
            return current
        parent = current.parent
        if parent == current:
            print(
                "Error: could not locate repository root "
                "(no .git or .claude directory found in any ancestor).",
                file=sys.stderr,
            )
            sys.exit(1)
        current = parent


def update_frontmatter_field(context_path: Path, field: str, value: str) -> None:
    """Set `field: value` in the YAML frontmatter block.

    Replaces an existing `field:` line if present; inserts before the closing ---
    if not.
    """
    text = context_path.read_text(encoding="utf-8")
    pattern = rf"^{re.escape(field)}:.*$"
    replacement = f"{field}: {value}"
    new_text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)

    if count == 0:
        # Field not in frontmatter — insert before the closing ---
        lines = new_text.split("\n")
        in_frontmatter = lines[0].strip() == "---" if lines else False
        inserted = False
        if in_frontmatter:
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    lines.insert(i, f"{field}: {value}")
                    inserted = True
                    break
        if not inserted:
            lines.append(f"{field}: {value}")
        new_text = "\n".join(lines)

    context_path.write_text(new_text, encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: find-spec-file.py <work-item-id> <context-file>", file=sys.stderr)
        sys.exit(1)

    work_item_id = sys.argv[1]
    context_path = Path(sys.argv[2])
    repo_root = find_repo_root()

    candidates = [
        p for p in repo_root.rglob("_spec_*.md")
        if ".git" not in p.parts
    ]

    matches = [
        p for p in candidates
        if work_item_id in p.read_text(encoding="utf-8")
    ]

    if not matches:
        print(
            f"Error: no _spec_*.md file found containing '{work_item_id}'.\n"
            f"Verify the work item ID is correct and you are on the right branch.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(matches) > 1:
        paths = "\n  ".join(str(m.relative_to(repo_root)) for m in matches)
        print(
            f"Error: multiple spec files found containing '{work_item_id}' — "
            f"cannot determine which to use:\n  {paths}\n"
            f"Resolve the ambiguity (e.g. deduplicate the task key) and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    spec_path = matches[0].relative_to(repo_root)
    update_frontmatter_field(context_path, "spec_path", str(spec_path).replace("\\", "/"))
    print(spec_path, flush=True)


if __name__ == "__main__":
    main()
