"""Rebase mechanic.

`rebase_onto()` fetches `origin`, rebases `working_branch` onto the freshly-fetched
`origin/<new_base>`, and either force-pushes with lease and returns "rebased" on a clean
rebase, or leaves the rebase in progress and returns "conflict" on a genuine conflict.
"""

import logging
import subprocess
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


def _run_git(args: list[str], worktree: Path, capture_output: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=worktree,
        timeout=30,
        check=True,
        capture_output=capture_output,
        text=capture_output,
    )


def rebase_onto(working_branch: str, new_base: str, worktree: Path) -> Literal["rebased", "conflict"]:
    _run_git(["fetch", "origin"], worktree)
    _run_git(["checkout", working_branch], worktree)
    try:
        _run_git(["rebase", f"origin/{new_base}"], worktree, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.debug("rebase_onto: rebase start failed, reporting as conflict: %s", e.stderr)
        return "conflict"
    _run_git(["push", "--force-with-lease", "origin", working_branch], worktree)
    return "rebased"
