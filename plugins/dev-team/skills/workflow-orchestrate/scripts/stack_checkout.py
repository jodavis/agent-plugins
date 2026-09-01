"""One-shot bootstrap for `monitor-prs`'s own worktree.

Per ADR-370 finding #1 (`_findings_GhStackSpike.md`), `gh stack`'s local stack-membership state
lives in the worktree-private `.git/worktrees/<name>/gh-stack` file. `monitor-prs` runs in its
own freshly spawned worktree — one that never registered any branch of its own into the stack via
`init`/`add` — so `gh stack view`/`sync` (and therefore `stack_pr_poll.py`) fail from it until
that local state is materialized. This script does exactly that: check out a real stack member
(never the trunk, which `gh-stack` doesn't consider a member) by PR number.

Takes a PR number, not a branch name: per `gh stack checkout --help`, only a PR number or PR URL
not yet tracked locally triggers gh-stack's own "discover the stack from the GitHub API, fetch its
branches, and set up the stack locally" fallback. A branch name only resolves against stacks
already tracked locally, which this worktree does not have yet.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT  # noqa: E402

_STACKED_PRS_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "work-with-stacked-prs" / "scripts"
)
sys.path.insert(0, str(_STACKED_PRS_SCRIPTS))
import gh_stack  # noqa: E402


def checkout(pr_number: int) -> None:
    status, detail = gh_stack.checkout(pr_number, cwd=REPO_ROOT)
    if status == "error":
        raise RuntimeError(f"gh stack checkout {pr_number} failed: {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pr_number", type=int)
    args = parser.parse_args()

    try:
        checkout(args.pr_number)
    except Exception as e:
        print(f"Error: could not check out the stack: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps("ok"))


if __name__ == "__main__":
    main()
