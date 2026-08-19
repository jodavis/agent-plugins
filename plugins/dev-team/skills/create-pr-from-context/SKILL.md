---
name: create-pr-from-context
user-invocable: false
description: >
  Use when creating a pull request for a work item using the workflow context file.
  Reads the context file, ensures the working branch, creates a PR, and writes the PR URL back to the context file.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are creating a pull request in GitHub for a work item and the task brief is in the workflow context file

You are reading from the context file, creating a new pull request in GitHub, and updating the context file.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief, ensure the working branch is set up, and retrieve the branch names from the context file.

### 3 — Check if PR already exists

If `pr_url` is already set in the context file, the PR has already been created. Output the PR URL and stop:

```json
{"pr_url": "<pr_url>"}
```

### 4 — Create the PR

Check the context file's `added_to_stack` frontmatter field (already available from step 2's
full context-file read) via this skill's own `scripts/pr_from_context.py` —
`should_submit_via_stack`/`resolve_submitted_pr_url` are unit-tested directly
(`test_pr_from_context.py`), covering both branches below and the PR-lookup failure mode, since
this SKILL.md is otherwise prose-only with no other way to exercise this decision logic:

```bash
python3 <skill-dir>/scripts/pr_from_context.py should-submit-via-stack "<added_to_stack>"
```

**If that prints `true`** — this task's branch is registered in a `gh stack`. Submit the
whole stack rather than constructing or passing any explicit `base`; `gh stack` already knows
this task's base from the `add` call `ensure-working-branch` made at registration time, and that
is the single source of truth — never a separately-read `base_branch` value. This is what closes
Issue-129 (PRs opening against the wrong base): there is no code path left where a stale/wrong
`base_branch` could produce a PR against `main`.

1. Run the `work-with-stacked-prs` skill's Preflight check, if it has not already been run this
   session.
2. Run the `work-with-stacked-prs` skill's `submit` operation — `gh_stack.py`'s
   `submit(auto=True, open_prs=False)` (or the CLI form `gh stack submit --auto`), matching
   `create-pr`'s existing `draft: true` convention. `submit` is always scoped to the entire
   stack — there is no per-branch flag — but this is safe to call unconditionally here: every
   entry below this task's newly-added one already has a real, open PR (guaranteed by
   `ensure-working-branch`'s lazy/recursive registration having pushed each ancestor branch
   already), so `submit` only *creates* a PR for the one entry that doesn't have one yet and is a
   no-op (idempotent) for the rest.
3. On failure, report the failure in detail — `submit()` failures are already typed
   `("error", detail)` per `gh_stack.py`'s docstring.
4. On success, resolve *this task's own* PR URL with a direct lookup (its schema is already
   well-known, unlike the stack `view` operation's per-branch `pr` object), piped straight into
   `resolve-submitted-pr-url` rather than a bare `jq '.[0].url'`:
   ```bash
   PR_LIST_JSON=$(gh pr list --head <working-branch> --json url)
   python3 <skill-dir>/scripts/pr_from_context.py resolve-submitted-pr-url "$PR_LIST_JSON"
   ```
   `jq '.[0].url'` on an empty array silently prints `null` with exit code 0, which would flow
   straight into step 5's `pr_url` frontmatter write with no error raised.
   `resolve-submitted-pr-url` raises instead: **on failure** (no matching PR found — `submit`
   may have succeeded but the PR isn't visible yet, or the head-branch name didn't match), report
   the failure in detail, the same as `submit`'s own failure path above; do not proceed to step 5.

**Otherwise** (`should-submit-via-stack` printed `false`) — unchanged: use the `create-pr` skill,
providing the `work-item-id`, working branch, `base_branch` (from the context file), and task
brief content. This is the fallback path for the one PR that's never part of a stack (the
feature's own spec PR), and for any task whose `ensure-working-branch` run fell through to the
non-stack path.

### 5 — Update the context file

Use the `use-context-file` skill to write the returned PR URL to the `pr_url` frontmatter field in the context file.

Use the `write-scratch-deliverable` skill to write the following in place of returning it as chat
text:

```json
{"pr_url": "https://github.com/..."}
```
