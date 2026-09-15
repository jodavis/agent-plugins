"""Thin `subprocess` wrapper around GitHub's `gh stack` CLI extension (`github/gh-stack`) — the
sole owner of every direct `gh stack` invocation in this pipeline, importable directly by any
bare script (no MCP involved). Every operation is non-interactive: explicit positional/flag
arguments only, never the interactive TUI, per `github/gh-stack`'s own agentic-use guidance.

Error-signaling convention (see ADR-371's task brief, Known ambiguity #3): every operation
returns a typed `("ok" | "error", detail)` tuple, mirroring `task_readiness.py`'s /
`pr_event_detector.py`'s existing `Literal`-status pattern in this codebase, rather than letting
`subprocess.CalledProcessError` propagate the way `rebase_mechanic.py` does. `view` is the only
operation `gh stack` itself supports `--json` for; its `detail` carries the parsed dict on
success. The other eight operations (`init`, `add`, `submit`, `sync`, `merge`, `rebase_continue`,
`checkout`, `link`) have no `--json` support — their outcome must be read from exit code/stderr
text; `detail` carries stripped stdout on success or stderr (falling back to stdout) on failure.

Caller contract (ADR-370 finding #1 — `_findings_GhStackSpike.md`): `gh stack`'s local
stack-membership state lives in the worktree-private `.git/worktrees/<name>/gh-stack` file, not
the shared common git directory, so it is **not** visible or correct across `git worktree`
checkouts of the same repository. Every function in this module **except `link`** must be called
from within the same worktree that owns the branch/stack in question — never from a different
worktree than the one that last registered it. This module does not assert that contract itself;
it is left to each caller (e.g. `ensure-working-branch`, `monitor-prs`) to honor. `link` is the
one deliberate exception: per `gh stack link --help`, it "does not rely on gh-stack local
tracking state" — it operates purely against GitHub (branch names, PR numbers, or PR URLs), so it
is safe to call from any worktree, including a task's own per-task worktree, with no shared-
worktree routing required.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60

GhStackStatus = Literal["ok", "error"]


def _run_gh_stack(
    args: list[str], cwd: Path | str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", "stack", *args],
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def _text_result(result: subprocess.CompletedProcess, op: str) -> tuple[GhStackStatus, str]:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        logger.debug("gh_stack.%s failed (exit %d): %s", op, result.returncode, detail)
        return ("error", detail)
    return ("ok", result.stdout.strip())


def init(
    branches: list[str] | None = None,
    base: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Anchor a new stack to a trunk branch. Adopts existing branches or creates missing ones.
    **Hard error (exit 5)** if the trunk is already anchored to a stack — confirmed by ADR-370 —
    callers must check-before-act rather than treat this as an idempotent no-op."""
    args = ["init"]
    if base:
        args += ["--base", base]
    args += list(branches or [])
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "init")


def add(
    branch: str | None = None,
    all_changes: bool = False,
    update_tracked: bool = False,
    message: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Create a new branch at HEAD, add it to the top of the stack, and check it out. Does
    **not** push — callers must push the new branch separately."""
    args = ["add"]
    if all_changes:
        args.append("-A")
    if update_tracked:
        args.append("-u")
    if message:
        args += ["-m", message]
    if branch:
        args.append(branch)
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "add")


def submit(
    auto: bool = True,
    open_prs: bool = False,
    remote: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Push and create/update PRs — **always scoped to the entire stack** (confirmed by
    ADR-370: no per-branch flag exists). `auto` defaults to `True` since `--auto` is required for
    non-interactive use; leave `open_prs=False` to default new PRs to draft."""
    args = ["submit"]
    if auto:
        args.append("--auto")
    if open_prs:
        args.append("--open")
    if remote:
        args += ["--remote", remote]
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "submit")


def sync(
    prune: bool = False,
    remote: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Fetch, cascade-rebase, push, and sync PR state for the current stack. Aborts cleanly with
    no changes (still exit 0) on non-interactive divergence, confirmed by ADR-370 — a `("ok",
    ...)` result does not always mean something changed. A genuine conflict exits non-zero."""
    args = ["sync"]
    if prune:
        args.append("--prune")
    if remote:
        args += ["--remote", remote]
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "sync")


def rebase_continue(
    cwd: Path | str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> tuple[GhStackStatus, str]:
    """Resume gh-stack's own cascading rebase across the remaining downstream branches after the
    currently-conflicted branch's git-level rebase has itself already been completed via a plain
    `git rebase --continue` (`resolve-rebase-conflict`'s own contract, unchanged). Per ADR-370's
    spike (`_findings_GhStackSpike.md`, section 3), this is not the same as a fresh `sync` call —
    `gh stack rebase --continue` specifically detects the git-level rebase is already done and
    resumes the cascade onto every branch still above it. Exit 0 means the whole cascade reached a
    clean state; a further non-zero exit means the cascade hit another conflict higher in the
    stack (same `.git/rebase-merge`/`.git/rebase-apply` shape as the first conflict) — callers
    should loop back into another conflict-resolution round exactly as they do for the first one."""
    return _text_result(
        _run_gh_stack(["rebase", "--continue"], cwd=cwd, timeout=timeout), "rebase_continue"
    )


def checkout(
    target: str | int, cwd: Path | str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> tuple[GhStackStatus, str]:
    """Check out a stack by stack number, PR number, PR URL, or branch name, materializing that
    stack's membership in the *current* worktree if it isn't already tracked there. Per `gh stack
    checkout --help`: a PR number or PR URL not yet tracked locally is discovered from the GitHub
    API and its branches fetched, so it works from a worktree that has never run `init`/`add` for
    this stack (unlike a branch name, which only resolves against locally tracked stacks). This is
    the only operation that can bootstrap `gh stack` awareness into a brand-new worktree — see
    ADR-370 finding #1 on why every worktree needs its own local stack-membership state."""
    return _text_result(_run_gh_stack(["checkout", str(target)], cwd=cwd, timeout=timeout), "checkout")


def view(
    short: bool = False, cwd: Path | str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> tuple[GhStackStatus, dict | str]:
    """Read current stack membership, branch ordering, and each entry's PR link/most-recent
    commit — the **only** operation that supports `--json`. On success, `detail` is the parsed
    dict (`trunk`, `currentBranch`, `branches[]`); on failure it's stderr text (or a JSON-decode
    error message if `--json` output couldn't be parsed)."""
    args = ["view", "--json"]
    if short:
        args.append("--short")
    result = _run_gh_stack(args, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        logger.debug("gh_stack.view failed (exit %d): %s", result.returncode, detail)
        return ("error", detail)
    try:
        return ("ok", json.loads(result.stdout))
    except json.JSONDecodeError as e:
        logger.debug("gh_stack.view: could not parse --json output: %s", e)
        return ("error", f"could not parse --json output: {e}")


def merge(
    target: str | None = None,
    yes: bool = True,
    merge_method: str | None = None,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Merge one or more PRs in the stack, all-or-nothing. `target` is a stack number or PR
    number (omit to merge the current branch's stack). `yes` defaults to `True` since `--yes` is
    required for non-interactive use. `merge_method` is one of `"merge"`, `"squash"`, `"rebase"`
    (passed via `--merge-method`); omit to use the last-used method."""
    args = ["merge"]
    if target:
        args.append(target)
    if yes:
        args.append("--yes")
    if merge_method:
        args += ["--merge-method", merge_method]
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "merge")


def link(
    *branches_or_prs: str,
    base: str | None = None,
    remote: str | None = None,
    open_prs: bool = False,
    cwd: Path | str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[GhStackStatus, str]:
    """Create or update a stack on GitHub purely from branch names, PR numbers, or PR URLs, in
    stack order (bottom to top) — **does not rely on gh-stack local tracking state**, unlike every
    other operation in this module (see the module docstring's caller contract). Branch arguments
    without an open PR are pushed and a new PR created automatically, with correct base-branch
    chaining; branch/PR arguments that already have an open PR just reuse it. If none of the
    arguments are already in a stack, a new one is created; if some already are, the existing
    stack is extended to include the rest (existing PRs are never removed).

    As a shortcut for growing an existing stack, pass its stack number (shown in the GitHub stack
    UI) as the first argument — the remaining arguments are appended to its top; arguments already
    in that stack are skipped.

    `base` sets the base branch for the bottom of a *new* stack (defaults to the repo's default
    branch) — irrelevant when growing an existing stack via the stack-number shortcut."""
    args = ["link", *branches_or_prs]
    if base:
        args += ["--base", base]
    if open_prs:
        args.append("--open")
    if remote:
        args += ["--remote", remote]
    return _text_result(_run_gh_stack(args, cwd=cwd, timeout=timeout), "link")


def check_gh_stack_extension_installed(timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Verify `gh extension list` includes `github/gh-stack` specifically — not some unrelated,
    same-named community extension. Parses the tab-separated `<command>\\t<owner/repo>\\t
    <version>` output and confirms the second field is literally `github/gh-stack`. Returns
    `False` (never raises) if the `gh` call itself fails."""
    result = subprocess.run(
        ["gh", "extension", "list"], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        logger.debug(
            "gh_stack.check_gh_stack_extension_installed: 'gh extension list' failed: %s",
            (result.stderr or result.stdout).strip(),
        )
        return False
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1] == "github/gh-stack":
            return True
    return False
