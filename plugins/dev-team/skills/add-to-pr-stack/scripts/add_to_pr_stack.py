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
  {"status": "not_applicable"}  - nothing to register: task isn't part of a tracked epic, has no
                                    local spec, has no declared dependency (its own PR is already
                                    correctly based on the feature branch directly), or its
                                    resolved dependency was completed outside the pipeline and has
                                    no context file of its own; stack_link_status written,
                                    added_to_stack stays false

`stack_link_status` (an extra_frontmatter key, not a named PipelineContext field, like
`working_branch`/`base_branch`/`parent_work_item`) is what makes a "not_applicable" outcome
durable across a crash-and-retry: `added_to_stack` alone can't distinguish "resolved, nothing to
do" from "never ran yet," since it's a plain boolean that only ever needs to become `True`.

Exits non-zero with a clear `Error: ...` message on stderr on any failure, including `link`
itself failing (e.g. a concurrent-registration race with a sibling task — this script does not
retry; see `SKILL.md` for why that's a known, accepted risk rather than engineered around here).
"""

import json
import subprocess
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


_MAX_STACK_DEPTH = 25


def _resolve_real_stack_chain(anchor_branch: str) -> list[str]:
    """Walk the PR base-ref chain starting at `anchor_branch`, downward through whichever
    earlier branches already have their own open PR, to build the real, current stack
    membership bottom-to-top (`anchor_branch` itself last).

    Uses plain `gh pr list` rather than `gh stack view`: gh-stack's own local tracking state
    is worktree-private (see `gh_stack.py`'s module docstring), and this script may run from a
    different worktree than the one that last registered the anchor's stack, so only a plain
    GitHub API read can be trusted here regardless of which worktree invoked it.

    Falls back to `[anchor_branch]` alone if the chain can't be resolved (e.g. `gh` is
    unavailable, unauthenticated, or `anchor_branch` unexpectedly has no open PR of its own) —
    the same single-anchor behavior this function replaces, so a lookup failure degrades safely
    instead of failing the whole add-to-pr-stack run."""
    chain: list[str] = []
    branch = anchor_branch
    seen: set[str] = set()
    for _ in range(_MAX_STACK_DEPTH):
        if not branch or branch in seen:
            break
        seen.add(branch)
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "baseRefName"],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            break
        if result.returncode != 0:
            break
        try:
            prs = json.loads(result.stdout)
        except json.JSONDecodeError:
            break
        if not prs:
            # `branch` has no open PR of its own — either it's the epic's feature/trunk
            # branch (never gets its own PR) or the lookup came up empty; either way, it's
            # not a stack member to include, so stop walking further down.
            break
        chain.append(branch)
        branch = prs[0].get("baseRefName", "")

    chain.reverse()
    return chain if chain else [anchor_branch]


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
        # No declared dependency: this task's own branch is based directly on the feature
        # branch (via ensure-working-branch), with no cross-PR stack relationship to
        # register yet — nothing becomes an anchor for anyone until a task that depends on
        # this one runs add_to_pr_stack itself. `gh stack link` also structurally requires
        # at least 2 positional branch/PR arguments (confirmed against the installed
        # extension), so a lone `working_branch` call here would always fail regardless (#256).
        ctx.extra_frontmatter["stack_link_status"] = "not_applicable"
        ctx.save(context_path)
        return {"status": "not_applicable"}

    anchor_path = compute_context_path(anchor_task, get_repo_slug())
    if not anchor_path.exists():
        # The anchor dependency was completed outside the dev-team pipeline entirely (e.g. a
        # human-owned task landed directly on the shared feature branch) — it has no context
        # file and therefore nothing of its own was ever registered into a gh stack. There is
        # nothing for this task to link onto either in that case (#271).
        ctx.extra_frontmatter["stack_link_status"] = "not_applicable"
        ctx.save(context_path)
        return {"status": "not_applicable"}

    anchor_branch_from_spec = PipelineContext.load(anchor_path).extra_frontmatter.get("working_branch", "")
    # Prefer this task's own recorded base_branch over re-deriving the anchor's branch from
    # the spec: ensure-working-branch sets base_branch from the same spec-derived anchor up
    # front, but a developer who fast-forwards this task's branch onto a later dependency
    # mid-implementation corrects base_branch to match — while the spec's own Depends-on line
    # (and therefore anchor_task/anchor_branch_from_spec) can be left stale (#276). base_branch
    # is this task's ground truth for what it's really built on right now.
    anchor_branch = base_branch or anchor_branch_from_spec
    if not anchor_branch or not working_branch:
        raise AddToPrStackError(
            f"anchor task '{anchor_task}' or this task is missing a working_branch"
        )
    # Resolve the anchor's real, current stack membership from GitHub rather than assuming
    # the immediate anchor is the only existing member below this task: an anchor that is
    # itself mid-stack (not the bottom) has earlier PRs below it that `link` must also be
    # given, or it refuses the update rather than risk dropping them (#273).
    stack_chain = _resolve_real_stack_chain(anchor_branch)
    status, detail = gh_stack.link(*stack_chain, working_branch)

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
