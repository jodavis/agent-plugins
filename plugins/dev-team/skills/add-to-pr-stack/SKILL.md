---
name: add-to-pr-stack
user-invocable: false
description: >
  Use after a task's PR has been signed off, to register it into its epic's `gh stack`. Runs
  `scripts/add_to_pr_stack.py`, which resolves the context file, links this task's already-open
  PR onto whichever of its own dependencies is furthest along the stack (or the feature branch,
  for the epic's first task), and writes `added_to_stack: true` back to the context file.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- A task's `signoff` step has just resolved `approved`, and its PR needs registering into the
  epic's `gh stack`

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

**This is the sole place a task's branch is ever registered into its epic's `gh stack`.**
`ensure-working-branch` deliberately never does this (see that skill's own intro) — registering
from a task's own per-task worktree would race against `monitor-stack`'s shared-worktree view of
the same stack, since `gh stack`'s local tracking state is worktree-private. This skill sidesteps
that entirely by using `gh stack link`, the one operation that doesn't need it — see
`work-with-stacked-prs/SKILL.md`'s cross-worktree caveat.

**Known concurrency risk, accepted rather than engineered around:** two sibling tasks in the same
epic reaching sign-off around the same time may call `link` against the same GitHub stack object
concurrently. `link`'s own contract ("existing PRs are never removed") makes this safe from data
loss, but the exact resulting stack order under a genuine race hasn't been verified empirically.
The script below does not retry a `link` failure — if it fails, report the failure in detail
rather than retrying blindly; a repeated failure on the same task most likely means something
other than a transient race.

## Steps

### 1 — Preflight

Run `work-with-stacked-prs`'s Preflight check if it hasn't already run earlier this session — the
script below shells out to `gh stack link` and needs the `github/gh-stack` extension installed.
This is the one genuinely interactive part of this skill (it may need to ask the user to install
the extension), which is why it isn't folded into the script itself.

### 2 — Run the script

```bash
python3 "<skill-dir>/scripts/add_to_pr_stack.py" "<work-item-id>"
```

It handles everything else: reading the context file, the "nothing to register" cases (task not
part of a tracked epic, or no local spec file — both report success with nothing to do), computing
which dependency to anchor on, resolving that dependency's own branch, running `link`, and writing
`added_to_stack`/a pending "Stack Link Result" deliverable on success.

Prints `{"status": "linked" | "not_applicable"}` as JSON to stdout on success — relay it verbatim
as your own final output (the script already wrote it to the pending-deliverable path
`write-scratch-deliverable` would have used, so no separate write step is needed here).

If it exits non-zero, it prints a clear `Error: ...` message to stderr — stop and report that
failure in detail (see the concurrency-risk note above for how to interpret a `link` failure
specifically).
