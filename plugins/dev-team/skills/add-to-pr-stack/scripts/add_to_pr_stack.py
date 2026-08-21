#!/usr/bin/env python3
"""Registers a task's already-signed-off PR into its epic's `gh stack`, via `gh stack link`.

Usage: add_to_pr_stack.py <work-item-id | context-file-path>

The sole place a task's branch is ever registered into a `gh stack` — deferred until sign-off,
using `link` specifically because `link` "does not rely on gh-stack local tracking state" (per
`gh stack link --help`), so it's safe to call from a task's own per-task worktree with no
shared-worktree routing (see `work-with-stacked-prs/SKILL.md`'s cross-worktree caveat and this
skill's own `SKILL.md` for why that matters).

Prints one of these as JSON on success:
  {"status": "linked"}          - registered; added_to_stack and stack_link_status written
  {"status": "not_applicable"}  - task isn't part of a tracked epic (or has no local spec);
                                    nothing to register; stack_link_status written, added_to_stack
                                    stays false

`stack_link_status` (an extra_frontmatter key, not a named PipelineContext field, like
`working_branch`/`base_branch`/`parent_work_item`) is what makes a "not_applicable" outcome
durable across a crash-and-retry: `added_to_stack` alone can't distinguish "resolved, nothing to
do" from "never ran yet," since it's a plain boolean that only ever needs to become `True`.

Exits non-zero with a clear `Error: ...` message on stderr on any failure, including `link`
itself failing (e.g. a concurrent-registration race with a sibling task — this script does not
retry; see `SKILL.md` for why that's a known, accepted risk rather than engineered around here).
"""

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_SKILLS_DIR = _SCRIPTS_DIR.parent.parent

sys.path.insert(0, str(_SKILLS_DIR / "workflow-orchestrate" / "scripts"))
from dev_team import compute_context_path  # noqa: E402
from get_context_path import get_repo_slug  # noqa: E402
from pipeline_context import PipelineContext  # noqa: E402
from task_dependencies import TaskDependencyError, parse_task_dependencies, validate_stack_order  # noqa: E402

sys.path.insert(0, str(_SKILLS_DIR / "ensure-working-branch" / "scripts"))
from stack_registration import compute_stack_anchor  # noqa: E402

sys.path.insert(0, str(_SKILLS_DIR / "work-with-stacked-prs" / "scripts"))
import gh_stack  # noqa: E402


class AddToPrStackError(RuntimeError):
    """Raised for any failure this script should stop and report in detail for."""


def resolve_context_path(argument: str) -> Path:
    """Same resolution rule `use-context-file`'s own prose uses: a `.md` suffix or an existing
    file is already the context-file path; otherwise treat it as a work-item-id."""
    if argument.endswith(".md") or Path(argument).is_file():
        return Path(argument)
    return compute_context_path(argument, get_repo_slug())


def write_pending_deliverable(context_path: Path, section_name: str, content: str) -> None:
    """Same convention `write-scratch-deliverable` uses — writes directly rather than delegating,
    since this script (unlike an LLM composing prose) can't "forget" the write after composing
    the content, the exact failure mode that skill exists to route around."""
    pending_dir = context_path.parent / ".pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    slug = section_name.replace(" ", "_")
    (pending_dir / f"{context_path.stem}__{slug}.md").write_text(content, encoding="utf-8")


def add_to_pr_stack(context_path: Path) -> dict:
    """Returns `{"status": "linked" | "not_applicable"}`. Raises `AddToPrStackError` on failure."""
    ctx = PipelineContext.load(context_path)

    if ctx.added_to_stack:
        return {"status": "linked"}
    already_resolved = ctx.extra_frontmatter.get("stack_link_status", "")
    if already_resolved:
        return {"status": already_resolved}

    parent_work_item = ctx.extra_frontmatter.get("parent_work_item", "")
    working_branch = ctx.extra_frontmatter.get("working_branch", "")
    base_branch = ctx.extra_frontmatter.get("base_branch", "")

    if not parent_work_item or not ctx.spec_path:
        ctx.extra_frontmatter["stack_link_status"] = "not_applicable"
        ctx.save(context_path)
        return {"status": "not_applicable"}

    try:
        spec_text = Path(ctx.spec_path).read_text(encoding="utf-8")
        order = validate_stack_order(spec_text)
        dependency_ids = parse_task_dependencies(spec_text).get(ctx.work_item_id, [])
    except OSError as e:
        raise AddToPrStackError(f"could not read spec file '{ctx.spec_path}': {e}") from e
    except TaskDependencyError as e:
        raise AddToPrStackError(f"could not compute stack order from '{ctx.spec_path}': {e}") from e

    anchor_task = compute_stack_anchor(ctx.work_item_id, dependency_ids, order)

    if anchor_task is None:
        if not working_branch or not base_branch:
            raise AddToPrStackError(
                "no anchor dependency, but working_branch/base_branch is missing from the "
                "context file — ensure-working-branch should have written both"
            )
        status, detail = gh_stack.link(working_branch, base=base_branch)
    else:
        anchor_path = compute_context_path(anchor_task, get_repo_slug())
        if not anchor_path.exists():
            raise AddToPrStackError(f"anchor task '{anchor_task}' has no context file yet")
        anchor_branch = PipelineContext.load(anchor_path).extra_frontmatter.get("working_branch", "")
        if not anchor_branch or not working_branch:
            raise AddToPrStackError(
                f"anchor task '{anchor_task}' or this task is missing a working_branch"
            )
        status, detail = gh_stack.link(anchor_branch, working_branch)

    if status != "ok":
        raise AddToPrStackError(f"gh stack link failed: {detail}")

    ctx.added_to_stack = True
    ctx.extra_frontmatter["stack_link_status"] = "linked"
    ctx.save(context_path)
    return {"status": "linked"}


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: add_to_pr_stack.py <work-item-id | context-file-path>", file=sys.stderr)
        sys.exit(1)

    context_path = resolve_context_path(sys.argv[1])
    if not context_path.exists():
        print(f"Error: context file not found: {context_path}", file=sys.stderr)
        sys.exit(1)

    try:
        result = add_to_pr_stack(context_path)
    except AddToPrStackError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    write_pending_deliverable(context_path, "Stack Link Result", json.dumps(result))
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
