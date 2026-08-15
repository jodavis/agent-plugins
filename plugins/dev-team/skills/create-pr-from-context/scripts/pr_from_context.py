"""Small testable decision points for create-pr-from-context/SKILL.md's step 4 (ADR-376).

`should_submit_via_stack` and `resolve_submitted_pr_url` back the branch choice and the
stack-submit PR-URL lookup step 4 asks a caller to make/act on, mirroring the small-testable-
Python-helper pattern `ensure-working-branch` already uses for its own step-4-shaped branching
logic (`stack_registration.py`), since this skill's own SKILL.md is otherwise prose-only.

Usage:
    pr_from_context.py should-submit-via-stack <added-to-stack>
    pr_from_context.py resolve-submitted-pr-url <pr-list-json>

`should-submit-via-stack` prints `true`/`false`. `resolve-submitted-pr-url` prints the resolved
PR URL. Both print a clear `Error: ...` message to stderr with a non-zero exit on failure — the
same convention `stack_registration.py`/`task_readiness.py` already use.
"""

import json
import sys


def should_submit_via_stack(added_to_stack: str) -> bool:
    """Whether step 4 should submit via `gh stack submit` rather than falling back to
    `create-pr`. `added_to_stack` is the raw context-file frontmatter string value the calling
    skill read (this skill has no Python module of its own reading `PipelineContext` directly) —
    case-insensitively `"true"`; anything else, including empty or absent, is not-in-stack,
    matching `PipelineContext`'s own frontmatter-parsing convention."""
    return added_to_stack.strip().lower() == "true"


class StackPrLookupError(RuntimeError):
    """Raised by `resolve_submitted_pr_url` when `gh pr list --head <branch> --json url` finds
    no matching PR — `submit` appeared to succeed but the PR isn't visible yet, or the head-
    branch name didn't match what was expected. Left unhandled, `jq '.[0].url'` on an empty array
    silently prints `null` with exit code 0, which would otherwise flow straight into step 5's
    `pr_url` frontmatter write with no error raised."""


def resolve_submitted_pr_url(pr_list_json: str) -> str:
    """Parse `gh pr list --head <working-branch> --json url`'s stdout and return the matching
    PR's URL, raising `StackPrLookupError` instead of silently returning `null` when the lookup
    found no match or the JSON itself is malformed."""
    try:
        entries = json.loads(pr_list_json)
    except json.JSONDecodeError as e:
        raise StackPrLookupError(f"could not parse `gh pr list` output as JSON: {e}") from e
    if not entries:
        raise StackPrLookupError(
            "`gh pr list --head <working-branch>` returned no matching PR after `gh stack "
            "submit` — the PR may not be visible yet, or the head-branch name didn't match."
        )
    return entries[0]["url"]


def _usage() -> None:
    print(
        "Usage: pr_from_context.py <should-submit-via-stack|resolve-submitted-pr-url> ...",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        _usage()

    subcommand, arg = sys.argv[1], sys.argv[2]
    if subcommand == "should-submit-via-stack":
        print("true" if should_submit_via_stack(arg) else "false")
    elif subcommand == "resolve-submitted-pr-url":
        try:
            print(resolve_submitted_pr_url(arg))
        except StackPrLookupError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        _usage()


if __name__ == "__main__":
    main()
