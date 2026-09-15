#!/usr/bin/env python3
"""Checks out a disposable local branch off a stacked PR's own branch tip, instead of the shared
stack branch itself — see `SKILL.md` for why this exists.

Usage: checkout_stack_pr_for_review.py <pr-number | pr-url | branch-name>

Resolves the argument to a head branch via `gh pr view` first (it accepts a bare branch name too,
so no argument-shape sniffing is needed); if that fails (no open PR for a plain branch name), the
argument is used directly as the head branch instead. Requires a clean `git status` before doing
anything — refuses to run in a dirty worktree. Creates `review/<pr-number-or-branch-slug>` off
the head branch's remote tip if it doesn't already exist locally, or resets it to that tip if it
does (a prior run of this script for the same PR).

Prints `{"branch": "<review-branch>", "pr_number": <int-or-null>, "head_branch": "<head-branch>"}`
as JSON to stdout on success. Exits non-zero with a clear `Error: ...` message on stderr on any
failure (dirty worktree, unresolvable ref, or any `git`/`gh` command failing).
"""

import json
import re
import subprocess
import sys


class CheckoutForReviewError(RuntimeError):
    """Raised for any failure this script should stop and report in detail for."""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def resolve_head_branch(argument: str) -> tuple[str, int | None]:
    """Returns `(head_branch, pr_number_or_None)`. Tries `gh pr view` first — it resolves a PR
    number, URL, or branch name uniformly — and falls back to treating `argument` as a bare
    branch name if that fails (a branch with no open PR yet is still a valid target)."""
    result = _run(["gh", "pr", "view", argument, "--json", "number,headRefName"])
    if result.returncode == 0:
        data = json.loads(result.stdout)
        return data["headRefName"], data["number"]
    return argument, None


def slugify_review_branch(head_branch: str, pr_number: int | None) -> str:
    if pr_number is not None:
        return f"review/pr-{pr_number}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", head_branch).strip("-")
    return f"review/{slug}"


def _local_branch_exists(branch: str) -> bool:
    result = _run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
    return result.returncode == 0


def checkout_for_review(argument: str) -> dict:
    status = _run(["git", "status", "--short"])
    if status.returncode != 0:
        raise CheckoutForReviewError(f"'git status --short' failed: {status.stderr.strip()}")
    if status.stdout.strip():
        raise CheckoutForReviewError(
            "worktree is not clean — refusing to touch it:\n" + status.stdout
        )

    head_branch, pr_number = resolve_head_branch(argument)

    fetch = _run(["git", "fetch", "origin", head_branch])
    if fetch.returncode != 0:
        raise CheckoutForReviewError(f"'git fetch origin {head_branch}' failed: {fetch.stderr.strip()}")

    review_branch = slugify_review_branch(head_branch, pr_number)

    if _local_branch_exists(review_branch):
        for cmd in (
            ["git", "checkout", review_branch],
            ["git", "reset", "--hard", f"origin/{head_branch}"],
        ):
            result = _run(cmd)
            if result.returncode != 0:
                raise CheckoutForReviewError(f"'{' '.join(cmd)}' failed: {result.stderr.strip()}")
    else:
        cmd = ["git", "checkout", "--no-track", "-b", review_branch, f"origin/{head_branch}"]
        result = _run(cmd)
        if result.returncode != 0:
            raise CheckoutForReviewError(f"'{' '.join(cmd)}' failed: {result.stderr.strip()}")

    return {"branch": review_branch, "pr_number": pr_number, "head_branch": head_branch}


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "Usage: checkout_stack_pr_for_review.py <pr-number | pr-url | branch-name>",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = checkout_for_review(sys.argv[1])
    except CheckoutForReviewError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
