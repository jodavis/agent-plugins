"""One-shot bootstrap for `monitor_prs.py`'s `bootstrapping` state — the auto-started stack-mode
path (`ctx.own_worktree == True`) only.

Per ADR-370 finding #1, `gh stack`'s local stack-membership state lives in the worktree-private
`.git/worktrees/<name>/gh-stack` file. A freshly auto-started monitor's worktree never registered
any branch of its own into the stack via `init`/`add`, so `gh stack view`/`sync` (and therefore
`stack_sync.py`/`stack_scan.py`) fail from it until that local state is materialized.

Consolidates what used to be monitor-prs's own prose step 2a into one tested script: derives the
epic's own spec/trunk branch from its context file's Project Configuration section (the same
template substitution `write-dev-spec` step 1.5 performs against
`git-repo.working-branches.task`/`git-repo.user-alias`), finds the bottom-most open PR based on
that trunk, and checks that stack member out via `stack_checkout.checkout()` — the one operation
that can materialize `gh-stack` awareness into a worktree that never ran `init`/`add` for this
stack.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dev_team import REPO_ROOT, _project_configuration  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402
from stack_checkout import checkout  # noqa: E402


def _feature_prefix(config: dict) -> str:
    """Substitute <user-alias> into git-repo.working-branches.task's template, then take the
    literal prefix up to the next <placeholder> (<task-work-item-id>) — e.g.
    "dev/<user-alias>/<task-work-item-id>-<slug>" with user-alias "jodavis" becomes
    "dev/jodavis/". Empty string if the template/user-alias aren't configured."""
    git_repo = config.get("git-repo", {})
    template = git_repo.get("working-branches", {}).get("task", "")
    user_alias = git_repo.get("user-alias", "")
    if not template or not user_alias:
        return ""
    substituted = template.replace("<user-alias>", user_alias)
    idx = substituted.find("<task-work-item-id>")
    return substituted[:idx] if idx != -1 else substituted


def _find_feature_branch(prefix: str, epic_id: str) -> str | None:
    subprocess.run(["git", "fetch", "origin"], cwd=REPO_ROOT, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "branch", "-r", "--sort=-committerdate"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    )
    pattern = re.compile(re.escape(prefix) + re.escape(epic_id) + r"-spec(-|$)")
    for line in result.stdout.splitlines():
        branch = line.strip()
        if branch.startswith("origin/"):
            branch = branch[len("origin/"):]
        if pattern.search(branch):
            return branch
    return None


def _find_bottom_pr(feature_branch: str) -> int | None:
    result = subprocess.run(
        ["gh", "pr", "list", "--base", feature_branch, "--state", "open",
         "--json", "number", "--jq", ".[0].number"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    pr_number_str = result.stdout.strip()
    if result.returncode != 0 or not pr_number_str:
        return None
    return int(pr_number_str)


def bootstrap(epic_id: str, context_path: Path) -> None:
    ctx = PipelineContext.load(context_path)
    config = _project_configuration(ctx)
    prefix = _feature_prefix(config)
    if not prefix:
        raise RuntimeError(
            "could not derive a feature-branch prefix from "
            "git-repo.working-branches.task/git-repo.user-alias"
        )

    feature_branch = _find_feature_branch(prefix, epic_id)
    if feature_branch is None:
        raise RuntimeError(
            f"no feature branch found for epic {epic_id} matching {prefix}{epic_id}(-|$)"
        )

    pr_number = _find_bottom_pr(feature_branch)
    if pr_number is None:
        raise RuntimeError(
            f"no open PR based directly on {feature_branch} for epic {epic_id}"
        )

    checkout(pr_number)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: stack_bootstrap.py <epic-id> <context-file>", file=sys.stderr)
        sys.exit(1)
    epic_id, context_file = sys.argv[1], sys.argv[2]

    try:
        bootstrap(epic_id, Path(context_file))
    except Exception as e:
        print(f"Error: could not bootstrap the stack: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps("ok"))


if __name__ == "__main__":
    main()
