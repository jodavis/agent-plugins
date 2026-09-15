---
name: checkout-stack-pr-for-review
user-invocable: false
description: >
  Use when you need to look at, manually test, or run a stacked PR's code locally — for review,
  debugging, or any ad hoc reason outside the automated pipeline. Runs
  `scripts/checkout_stack_pr_for_review.py`, which creates a new throwaway local branch off the
  PR's own branch tip instead of checking out the shared stack branch itself.
argument-hint: <pr-number | pr-url | branch-name>
---

Use this skill when:
- A human, or any process outside the automated `/implement`/`/fix`/`monitor-stack` pipeline,
  wants to check out a task's PR to read, run, or manually test its code
- You're about to run `git checkout <some-stacked-branch>` for any ad hoc reason and pause to ask
  "is this branch actually mine to check out?"

Do NOT use this skill when:
- You're the `dev-team:developer` agent already running inside a task's own pipeline worktree —
  that branch is already yours; there's nothing to "review" a copy of
- You're `monitor-stack` — it owns the epic's one shared worktree and checks out real stack
  members directly, by design (see `work-with-stacked-prs/SKILL.md`'s cross-worktree caveat)

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

**Why this exists:** a task's own working branch and the epic's `gh stack` are both actively
managed by other processes for as long as the epic is in flight — `implement` (via its own
per-task worktree) while the task is active, and `add-to-pr-stack`/`monitor-stack` (via the
epic's shared worktree) once it's signed off and linked. Checking out a stacked branch directly
from a *third* location risks exactly the collision this skill exists to prevent: an uncommitted
local change, a stray commit, or a half-finished rebase left on a branch one of those other
processes expects to find clean and already at a known commit. A throwaway branch off the same
tip gives you the identical code with none of that risk.

## Steps

### 1 — Run the script

```bash
python3 "<skill-dir>/scripts/checkout_stack_pr_for_review.py" "<argument>"
```

It handles everything: resolving the argument (PR number, PR URL, or branch name) to a head
branch via `gh pr view`, falling back to using it directly as a branch name if that fails, the
worktree-freshness hard stop, fetching, and creating (or resetting, if this skill already ran for
the same PR) `review/<pr-number-or-branch-slug>` off the head branch's remote tip.

Prints `{"branch": ..., "pr_number": ..., "head_branch": ...}` as JSON on success. If it exits
non-zero, it prints a clear `Error: ...` message to stderr — stop and report that failure in
detail (a dirty worktree, an unresolvable ref, or a `git`/`gh` command failing).

### 2 — Report, with the constraints that make this safe

Respond with the branch name from step 1, and these two rules — restate them explicitly, since
the whole point of this skill is that violating either one reintroduces the exact collision it
exists to prevent:

- **Never push the review branch.** It has no relationship to the epic's `gh stack` and pushing
  it would just create a stray, untracked branch on the remote.
- **Never run any `gh stack` operation (`init`/`add`/`submit`/`sync`/`link`/`checkout`/`merge`/
  `rebase --continue`) from this checkout.** This branch is a disposable copy for reading/running
  code only — it is not a stack member, and treating it as one is exactly the mistake this skill
  exists to prevent.
