#!/usr/bin/env python3
"""Working-branch base selection and branch-identity verification for `ensure-working-branch`.

`ensure-working-branch` is a prose-only skill (its own `SKILL.md`, no Python module of its own)
that invokes this script via `Bash` for its two pieces of genuinely branching decision logic:

- `anchor`: given this task's own work-item id and its epic's spec file, pick which of this
  task's own declared dependencies its working branch should be based on (plain git — this task
  is never registered into the epic's `gh stack` here; see `add-to-pr-stack`, which is the sole
  place that happens, after sign-off).
- `verify`: the closes-#126 guardrail — confirm the branch actually checked out is genuinely
  this task's own working branch, and never the shared feature branch.

Usage:
    stack_registration.py anchor <work-item-id> <spec-path>
    stack_registration.py verify <current-branch> <working-branch> <feature-branch>

`anchor` prints `{"anchor_task": <id-or-null>}` as JSON to stdout on success. `verify` prints
nothing on success. Both print a clear `Error: ...` message to stderr with a non-zero exit on
failure — the same convention `task_readiness.py`/`task_dependencies.py` already use so a prose
skill with no other way to call a Python function directly can invoke this via `Bash`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "workflow-orchestrate" / "scripts"))
from task_dependencies import TaskDependencyError, parse_task_dependencies, validate_stack_order  # noqa: E402


def compute_stack_anchor(
    task_work_item_id: str,
    dependency_ids: list[str],
    order: list[str],
) -> str | None:
    """Pick which of this task's own declared dependencies its working branch (and, later, its
    `add-to-pr-stack` `link` call) should be based on: whichever dependency sorts latest in the
    epic's document order (`validate_stack_order`) — a linear stack transitively contains
    everything sorted before it, so basing on the latest one is sufficient regardless of how many
    dependencies there are. Returns `None` when the task has no declared dependencies at all — it
    should be based on the feature branch directly instead.

    Every dependency named here is guaranteed already `done` (fully signed off and linked into
    the stack via `add-to-pr-stack`) by the time this task starts — `task_readiness.py`'s
    `is_task_eligible` gates on exactly that — so there is no backfill/placeholder concern the way
    the old eager-registration design had: an ancestor that hasn't started yet is never a real
    dependency of a task that's already eligible to run.
    """
    if not dependency_ids:
        return None
    return max(dependency_ids, key=lambda dep_id: order.index(dep_id))


class BranchIdentityMismatchError(RuntimeError):
    """Raised by `verify_branch_identity` when the branch actually checked out after
    registration doesn't match the computed working-branch name — including, especially, when
    it's silently the shared feature branch instead (the exact conflation bug closed by #126)."""


def verify_branch_identity(current_branch: str, working_branch: str, feature_branch: str) -> None:
    """Hard-stop guardrail run immediately after registering a task's branch: confirm HEAD is
    genuinely `working_branch`, and never `feature_branch` (closes #126 — an agent mistaking the
    shared feature branch for its own working branch)."""
    if current_branch == feature_branch:
        raise BranchIdentityMismatchError(
            f"HEAD is on the feature branch '{feature_branch}' instead of this task's own "
            f"working branch '{working_branch}' — registration must have failed to create or "
            f"check out the new branch (closes #126)."
        )
    if current_branch != working_branch:
        raise BranchIdentityMismatchError(
            f"HEAD is on '{current_branch}', not the computed working branch '{working_branch}'."
        )


def _run_anchor(argv: list[str]) -> None:
    if len(argv) != 2:
        print("Usage: stack_registration.py anchor <work-item-id> <spec-path>", file=sys.stderr)
        sys.exit(1)
    task_work_item_id, spec_path = argv

    try:
        spec_text = Path(spec_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error: could not read spec file '{spec_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        order = validate_stack_order(spec_text)
        dependency_ids = parse_task_dependencies(spec_text).get(task_work_item_id, [])
    except TaskDependencyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if task_work_item_id not in order:
        print(
            f"Error: '{task_work_item_id}' is not present in the stack order: {order}",
            file=sys.stderr,
        )
        sys.exit(1)

    anchor_task = compute_stack_anchor(task_work_item_id, dependency_ids, order)
    print(json.dumps({"anchor_task": anchor_task}), flush=True)


def _run_verify(argv: list[str]) -> None:
    if len(argv) != 3:
        print(
            "Usage: stack_registration.py verify <current-branch> <working-branch> <feature-branch>",
            file=sys.stderr,
        )
        sys.exit(1)
    current_branch, working_branch, feature_branch = argv

    try:
        verify_branch_identity(current_branch, working_branch, feature_branch)
    except BranchIdentityMismatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("anchor", "verify"):
        print("Usage: stack_registration.py <anchor|verify> ...", file=sys.stderr)
        sys.exit(1)

    subcommand, *rest = sys.argv[1:]
    if subcommand == "anchor":
        _run_anchor(rest)
    else:
        _run_verify(rest)


if __name__ == "__main__":
    main()
