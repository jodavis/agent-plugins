#!/usr/bin/env python3
"""Lazy, recursive stack branch registration for `ensure-working-branch` (ADR-375).

`ensure-working-branch` is a prose-only skill (its own `SKILL.md`, no Python module of its own)
that invokes this script via `Bash` for its two pieces of genuinely branching decision logic:

- `plan`: given this task's own work-item id and its epic's spec file, compute which tasks
  (this one, plus any not-yet-registered ancestors) need a branch registered in the stack
  before this task's own branch can be created, in the order they must be registered.
- `verify`: the closes-#126 guardrail — confirm the branch actually checked out after
  registration is genuinely this task's own working branch, and never the shared feature
  branch.

Usage:
    stack_registration.py plan <work-item-id> <spec-path>
    stack_registration.py verify <current-branch> <working-branch> <feature-branch>

`plan` prints `{"plan": [...], "anchor_task": <id-or-null>}` as JSON to stdout on success.
`verify` prints nothing on success. Both print a clear `Error: ...` message to stderr with a
non-zero exit on failure — the same convention `task_readiness.py`/`task_dependencies.py`
already use so a prose skill with no other way to call a Python function directly can invoke
this via `Bash`.
"""

import json
import sys
from pathlib import Path
from typing import Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "workflow-orchestrate" / "scripts"))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402
from task_dependencies import TaskDependencyError, validate_stack_order  # noqa: E402


class RegistrationPlan(NamedTuple):
    """The result of `compute_registration_plan`.

    `plan` is the ordered list of task-work-item ids that need a branch registered before (and
    including) the target task, oldest ancestor first. `anchor_task` is the id of the
    already-registered task whose branch `plan[0]` should be based on, or `None` when `plan[0]`
    is the very first task in the epic's stack order (base off the feature branch itself
    instead)."""

    plan: list[str]
    anchor_task: str | None


def compute_registration_plan(
    task_work_item_id: str,
    order: list[str],
    is_registered: Callable[[str], bool],
) -> RegistrationPlan:
    """Walk backward from `task_work_item_id`'s position in `order` until an already-registered
    ancestor is found (or the start of the stack is reached), then return every task from that
    point forward through `task_work_item_id` itself — the tasks that need a branch registered,
    oldest first. Never checks whether any real `Depends on:` dependency is ready; this is
    purely structural stack position (see ADR-375's "lazy, recursive, and decoupled from real-
    dependency readiness" design decision).

    Raises ValueError if `task_work_item_id` is not present in `order`.
    """
    if task_work_item_id not in order:
        raise ValueError(f"'{task_work_item_id}' is not present in the stack order: {order}")

    index = order.index(task_work_item_id)
    start = index
    while start > 0 and not is_registered(order[start - 1]):
        start -= 1

    anchor_task = order[start - 1] if start > 0 else None
    return RegistrationPlan(plan=order[start : index + 1], anchor_task=anchor_task)


def is_added_to_stack(task_work_item_id: str) -> bool:
    """Whether `task_work_item_id` already has `added_to_stack: true` on its own context file.
    A task with no context file yet (an unstarted human task) is never registered."""
    path = compute_context_path(task_work_item_id, get_repo_slug())
    if not path.exists():
        return False
    return PipelineContext.load(path).added_to_stack


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


def _run_plan(argv: list[str]) -> None:
    if len(argv) != 2:
        print("Usage: stack_registration.py plan <work-item-id> <spec-path>", file=sys.stderr)
        sys.exit(1)
    task_work_item_id, spec_path = argv

    try:
        spec_text = Path(spec_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error: could not read spec file '{spec_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        order = validate_stack_order(spec_text)
    except TaskDependencyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = compute_registration_plan(task_work_item_id, order, is_registered=is_added_to_stack)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps({"plan": result.plan, "anchor_task": result.anchor_task}), flush=True)


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
    if len(sys.argv) < 2 or sys.argv[1] not in ("plan", "verify"):
        print("Usage: stack_registration.py <plan|verify> ...", file=sys.stderr)
        sys.exit(1)

    subcommand, *rest = sys.argv[1:]
    if subcommand == "plan":
        _run_plan(rest)
    else:
        _run_verify(rest)


if __name__ == "__main__":
    main()
