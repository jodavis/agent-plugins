#!/usr/bin/env python3
"""Set up the git working branch for a dev-team pipeline run.

Usage: prepare-working-branch.py <context-file>

Reads base_branch and work_item_id from the context file frontmatter.
Computes the working branch as dev/claude/<work_item_id>.

Branch handling:
  - Already on working branch           → pull latest from remote
  - Working branch exists, not checked out,
    but IS an ancestor of HEAD          → stay; HEAD is already ahead
  - Working branch exists, not checked out → check out, then pull
  - Working branch does not exist       → check out base branch, pull,
                                          then create working branch

Exits 0 on success, 1 on failure.
"""

import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}
    metadata: dict = {}
    for line in lines[1:end]:
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return metadata


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True)


def current_branch() -> str:
    result = run("git", "branch", "--show-current")
    return result.stdout.strip()


def local_branch_exists(branch: str) -> bool:
    result = run("git", "branch", "--list", branch)
    return bool(result.stdout.strip())


def remote_branch_exists(branch: str) -> bool:
    result = run("git", "branch", "-r", "--list", f"origin/{branch}")
    return bool(result.stdout.strip())


def is_ancestor_of_head(branch: str) -> bool:
    """Return True if <branch> tip is an ancestor of HEAD.

    If HEAD is already at a commit descended from the working branch (e.g. we
    branched further off it), checking out the working branch would move us
    backwards. In that case we stay put.
    """
    result = run("git", "merge-base", "--is-ancestor", branch, "HEAD")
    return result.returncode == 0


def checkout(branch: str) -> None:
    result = run("git", "checkout", branch)
    if result.returncode != 0:
        print(f"Error: could not check out '{branch}': {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def pull(branch: str) -> None:
    result = run("git", "pull", "origin", branch)
    if result.returncode != 0:
        # Pull failure is non-fatal if the branch is new on the remote
        print(f"Warning: pull failed for '{branch}' (may be a new branch): {result.stderr.strip()}", file=sys.stderr)


def create_branch(branch: str) -> None:
    result = run("git", "checkout", "-b", branch)
    if result.returncode != 0:
        print(f"Error: could not create branch '{branch}': {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: prepare-working-branch.py <context-file>", file=sys.stderr)
        sys.exit(1)

    context_path = Path(sys.argv[1])
    if not context_path.exists():
        print(f"Error: context file not found: {context_path}", file=sys.stderr)
        sys.exit(1)

    meta = parse_frontmatter(context_path.read_text(encoding="utf-8"))
    work_item_id = meta.get("work_item_id", "").strip()
    base_branch = meta.get("base_branch", "").strip()

    if not work_item_id:
        print("Error: work_item_id not found in context file frontmatter.", file=sys.stderr)
        sys.exit(1)
    if not base_branch:
        print("Error: base_branch not found in context file frontmatter.", file=sys.stderr)
        sys.exit(1)

    working_branch = f"dev/claude/{work_item_id}"

    # Fetch so local knowledge of remote branches is current
    fetch = run("git", "fetch", "origin")
    if fetch.returncode != 0:
        print(f"Warning: git fetch failed: {fetch.stderr.strip()}", file=sys.stderr)

    exists_locally = local_branch_exists(working_branch)
    exists_remotely = remote_branch_exists(working_branch)

    if exists_locally or exists_remotely:
        on_it = current_branch() == working_branch
        if on_it:
            # Already there — just sync
            if exists_remotely:
                pull(working_branch)
        else:
            checkout(working_branch)
            if exists_remotely:
                pull(working_branch)
    else:
        # Working branch doesn't exist yet — create it from the base branch
        base_exists_locally = local_branch_exists(base_branch)
        base_exists_remotely = remote_branch_exists(base_branch)
        
        if not base_exists_locally and not base_exists_remotely:
            print(
                f"Error: base branch '{base_branch}' does not exist locally or on remote.",
                file=sys.stderr,
            )
            sys.exit(1)
        checkout(base_branch)
        if (base_exists_remotely):
            pull(base_branch)
        create_branch(working_branch)

    print(f"Ready on branch: {current_branch()}", flush=True)


if __name__ == "__main__":
    main()
