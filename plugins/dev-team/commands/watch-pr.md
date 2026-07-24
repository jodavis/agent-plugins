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

Then stop.
