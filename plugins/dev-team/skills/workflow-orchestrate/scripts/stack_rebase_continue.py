"""One-shot follow-up to `resolve-rebase-conflict` for a multi-branch `gh stack` cascade.

Per ADR-370's spike (`_findings_GhStackSpike.md`, section 3), completing the currently-conflicted
branch's own git-level rebase (`resolve-rebase-conflict`'s unchanged `git rebase --continue`
contract) is not enough to reconcile a multi-branch stack — downstream branches are left
un-rebased until `gh stack rebase --continue` specifically resumes gh-stack's own cascade. This
script makes exactly that one call and reports whether the cascade reached a clean state or hit
another conflict further up the stack, mirroring `stack_pr_poll.py`'s own conflict-detection
shape so `monitor-stack` can react to both the same way.
"""

import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT  # noqa: E402
from stack_pr_poll import _rebase_in_progress  # noqa: E402

_STACKED_PRS_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "work-with-stacked-prs" / "scripts"
)
sys.path.insert(0, str(_STACKED_PRS_SCRIPTS))
import gh_stack  # noqa: E402


def rebase_continue() -> Literal["conflict", "ok"]:
    status, detail = gh_stack.rebase_continue(cwd=REPO_ROOT)
    if _rebase_in_progress(REPO_ROOT):
        return "conflict"
    if status == "error":
        raise RuntimeError(f"gh stack rebase --continue failed: {detail}")
    return "ok"


def main() -> None:
    try:
        result = rebase_continue()
    except Exception as e:
        print(f"Error: could not resume the stack's rebase cascade: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
