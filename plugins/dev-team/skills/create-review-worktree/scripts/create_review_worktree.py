#!/usr/bin/env python3
"""Deterministic classification and cross-repo execution logic behind the create-review-worktree
skill.

Given `resolve-pr-reference`'s resolved-PR JSON (`owner`, `repo`, `number`, `pr_url`, ...), this
module decides which of the three isolation mechanisms applies — `enterworktree` (same-repo),
`sibling-worktree` (cross-repo with a matching `../<repo>` sibling clone), or `scratch-clone`
(cross-repo fallback) — and, for the two cross-repo mechanisms, performs the actual `git`/`gh`
commands to stand up the working copy.

The same-repo mechanism itself is deliberately NOT implemented here: it requires calling the
native `EnterWorktree` tool, which — like `ExitWorktree` elsewhere in this plugin — is only
callable from the agent's own tool-use turn, never from a script. `create-review-worktree/
SKILL.md` calls `EnterWorktree` directly, then runs the same `gh pr checkout` + `git rev-parse`
pair this module uses for the cross-repo paths, inline as thin prose (a simple call-through, no
branching, so it needs no dedicated test of its own).

CLI usage:
    python3 create_review_worktree.py classify '<resolved-pr-json>'
    python3 create_review_worktree.py finish-cross-repo '<resolved-pr-json>'

Both print one JSON object to stdout on success, or "Error: ..." to stderr and exit 1 on failure.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_GIT_TIMEOUT = 30
_GH_TIMEOUT = 120


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def parse_owner_repo(remote_url: str) -> tuple[str, str]:
    """Extracts (owner, repo) from any of the four common git remote URL forms, reusing the same
    regex convention as `use-context-file/scripts/compute-context-file.py`'s repo-slug parsing."""
    slug = re.sub(r"^https?://[^/]+/", "", remote_url)
    slug = re.sub(r"^[^@]+@[^:]+:", "", slug)
    slug = re.sub(r"\.git$", "", slug)
    owner, _, repo = slug.rpartition("/")
    return owner, repo


def get_current_repo(cwd: Path) -> tuple[str, str]:
    """Returns (owner, repo) for the repo `git remote get-url origin` points to in `cwd`."""
    result = _run(["git", "remote", "get-url", "origin"], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"could not read git remote 'origin' in {cwd}: {result.stderr.strip()}")
    return parse_owner_repo(result.stdout.strip())


def get_repo_root(cwd: Path | None = None) -> Path:
    """Returns the top-level directory of the git repo `cwd` (or the process cwd) is in."""
    result = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"could not determine repo root: {result.stderr.strip()}")
    return Path(result.stdout.strip())


def sibling_matches(sibling_dir: Path, owner: str, repo: str) -> bool:
    """Whether `sibling_dir` is a git repo whose own `origin` remote names `owner/repo` — the
    conventional `../<repo>` sibling-clone check, case-insensitive to match GitHub's own
    case-insensitive owner/repo matching."""
    if not (sibling_dir / ".git").exists():
        return False
    result = _run(["git", "remote", "get-url", "origin"], cwd=sibling_dir)
    if result.returncode != 0:
        return False
    sib_owner, sib_repo = parse_owner_repo(result.stdout.strip())
    return sib_owner.lower() == owner.lower() and sib_repo.lower() == repo.lower()


def classify_isolation(resolved: dict, repo_root: Path) -> dict:
    """Decides which isolation mechanism applies for `resolved` (a `resolve-pr-reference`
    `status: resolved` payload), given `repo_root` — the current session's own repo root.

    Returns one of:
        {"repo_scope": "same-repo", "isolation_kind": "enterworktree"}
        {"repo_scope": "cross-repo", "isolation_kind": "sibling-worktree", "sibling_path": "..."}
        {"repo_scope": "cross-repo", "isolation_kind": "scratch-clone"}
    """
    current_owner, current_repo = get_current_repo(repo_root)
    if resolved["owner"].lower() == current_owner.lower() and resolved["repo"].lower() == current_repo.lower():
        return {"repo_scope": "same-repo", "isolation_kind": "enterworktree"}

    sibling_dir = repo_root.parent / resolved["repo"]
    if sibling_matches(sibling_dir, resolved["owner"], resolved["repo"]):
        return {
            "repo_scope": "cross-repo",
            "isolation_kind": "sibling-worktree",
            "sibling_path": str(sibling_dir),
        }

    return {"repo_scope": "cross-repo", "isolation_kind": "scratch-clone"}


def _scratch_dir_name(owner: str, repo: str, number: int) -> str:
    return f"review-{owner}-{repo}-{number}"


def _checkout_pr_head(target_dir: Path, owner: str, repo: str, number: int) -> str:
    """Runs `gh pr checkout` in `target_dir` to move it onto the PR's actual head, then returns
    the resulting local branch name via `git rev-parse --abbrev-ref HEAD`."""
    checkout = _run(
        ["gh", "pr", "checkout", str(number), "-R", f"{owner}/{repo}"],
        cwd=target_dir,
        timeout=_GH_TIMEOUT,
    )
    if checkout.returncode != 0:
        raise RuntimeError(f"gh pr checkout failed: {checkout.stderr.strip()}")

    head_ref = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=target_dir)
    if head_ref.returncode != 0:
        raise RuntimeError(f"could not determine checked-out ref: {head_ref.stderr.strip()}")
    return head_ref.stdout.strip()


def finish_cross_repo(resolved: dict, repo_root: Path) -> dict:
    """Stands up the working copy for a cross-repo resolved PR — `git worktree add` from a
    matching sibling clone, or `gh repo clone` into a scratch directory when no sibling matches —
    then checks it out to the PR's actual head. Raises `ValueError` if `resolved` is actually
    same-repo (this function is cross-repo-only; the same-repo mechanism belongs to the calling
    skill's own `EnterWorktree` step, not this module)."""
    classification = classify_isolation(resolved, repo_root)
    if classification["repo_scope"] != "cross-repo":
        raise ValueError("finish_cross_repo() called for a same-repo resolved PR")

    owner, repo, number = resolved["owner"], resolved["repo"], resolved["number"]
    target_dir = repo_root / ".claude" / "worktrees" / _scratch_dir_name(owner, repo, number)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if classification["isolation_kind"] == "sibling-worktree":
        sibling_dir = Path(classification["sibling_path"])
        result = _run(
            ["git", "worktree", "add", "--detach", str(target_dir), "HEAD"],
            cwd=sibling_dir,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {result.stderr.strip()}")
    else:
        result = _run(
            ["gh", "repo", "clone", f"{owner}/{repo}", str(target_dir)],
            timeout=_GH_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gh repo clone failed: {result.stderr.strip()}")

    head_ref = _checkout_pr_head(target_dir, owner, repo, number)

    return {
        "isolation_kind": classification["isolation_kind"],
        "worktree_path": str(target_dir),
        "head_ref": head_ref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("resolved", help="JSON payload from resolve-pr-reference")
    args = parser.parse_args(argv)

    try:
        resolved = json.loads(args.resolved)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        return 1

    try:
        repo_root = get_repo_root()
        if args.command == "classify":
            output = classify_isolation(resolved, repo_root)
        elif args.command == "finish-cross-repo":
            output = finish_cross_repo(resolved, repo_root)
        else:
            print(f"Error: unknown command {args.command!r}", file=sys.stderr)
            return 1
    except (RuntimeError, ValueError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
