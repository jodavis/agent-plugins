"""Rebase mechanic.

`rebase_onto()` fetches `origin`, rebases `working_branch` onto the freshly-fetched
`origin/<new_base>`, and either force-pushes with lease and returns "rebased" on a clean
rebase, or leaves the rebase in progress and returns "conflict" on a genuine conflict.
"""

import subprocess
from pathlib import Path
from typing import Literal


def _run_git(args: list[str], worktree: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=worktree, timeout=30, check=True)


def rebase_onto(working_branch: str, new_base: str, worktree: Path) -> Literal["rebased", "conflict"]:
    _run_git(["fetch", "origin"], worktree)
    _run_git(["checkout", working_branch], worktree)
    try:
        _run_git(["rebase", f"origin/{new_base}"], worktree)
    except subprocess.CalledProcessError:
        return "conflict"
    _run_git(["push", "--force-with-lease", "origin", working_branch], worktree)
    return "rebased"
