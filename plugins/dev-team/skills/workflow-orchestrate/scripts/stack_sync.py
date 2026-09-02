"""Runs `gh stack sync` for `monitor_prs.py`'s `syncing_stack` state.

Factored out of `stack_pr_poll.py`'s combined sync+scan loop so `SyncingStackStep` can dispatch
and observe the sync operation as its own state, independently of scanning for stack events
(`ScanningStackEventsStep`, in `stack_scan.py`). Reuses `stack_pr_poll._rebase_in_progress()`
rather than duplicating it — that module's own conflict-detection helper is the single source of
truth both scripts rely on.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT  # noqa: E402
from stack_pr_poll import _rebase_in_progress  # noqa: E402

_STACKED_PRS_SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "work-with-stacked-prs" / "scripts"
)
sys.path.insert(0, str(_STACKED_PRS_SCRIPTS))
import gh_stack  # noqa: E402


def sync() -> str:
    """Run `gh stack sync` in the current worktree. Returns "conflict" if the cascade left a
    rebase mid-flight, else "synced"."""
    gh_stack.sync(cwd=REPO_ROOT)
    if _rebase_in_progress(REPO_ROOT):
        return "conflict"
    return "synced"


def main() -> None:
    try:
        result = sync()
    except Exception as e:
        print(f"Error: could not sync the stack: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
