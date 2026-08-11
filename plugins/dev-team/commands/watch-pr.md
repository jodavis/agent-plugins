---
description: Manually start the post-hand-off PR monitor for a task whose PR is already open, when it was not auto-started.
argument-hint: <task key, e.g. ADR-123>
---

## Request

$ARGUMENTS

## Steps

### 1 — Determine work item ID

Extract the `[A-Z]+-\d+` task key from the arguments. If no match is found, tell the user:

> Please provide a task key (e.g. ADR-123).

Then stop.

### 2 — Spawn the monitor

This command's only job is spawning `dev-team:watch-pr` in its own fresh, isolated worktree — the
manual fallback for when `concurrent-orchestrate`'s auto-start never happened (e.g. its own
session was interrupted before reaching hand-off for this task). A bare skill invocation from
this session would get no isolation at all, so the spawn itself is what gives the monitor the
same isolation guarantee the auto-started path has.

```
Agent(
  subagent_type: "claude",
  isolation: "worktree",
  prompt: "Invoke the `watch-pr` skill with arguments:
--work-item-id <work-item-id>"
)
```

Once the spawn call returns its worktree branch, rename it to `watch-<work-item-id>` — the same
task-identifying convention `concurrent-orchestrate`'s auto-start path uses (see its **Worktree
naming** section), so a manually-started monitor's worktree is just as identifiable in
`git worktree list` as an auto-started one:

```bash
git branch -m <raw-branch-name> watch-<work-item-id>
```

If it fails because `watch-<work-item-id>` already exists (a stale leftover from an earlier
monitor for the same task that was never cleaned up), fall back to a disambiguated name instead:

```bash
git branch -m <raw-branch-name> watch-<work-item-id>-<raw-branch-suffix>
```

using the last segment of `<raw-branch-name>` (its 8-hex-char suffix) to disambiguate. If the
rename fails for any other reason (git lock, unexpected error, etc.), this is a **hard stop**:
stop immediately and report the failure in detail rather than proceeding with an unrenamed
worktree. This rename is run from your own (non-worktree) checkout, never from inside the spawned
worktree — it only renames a ref, so it never touches the worktree's files. `watch-pr`'s own
step 2 records this renamed name as `watch_worktree_branch` by reading its own current branch
*before* checking out `working_branch` — reading it any later would return `working_branch`
instead, once `watch-pr` step 2's checkout has switched HEAD away from the renamed branch — no
further action needed here.

Then stop.
