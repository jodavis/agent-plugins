---
description: Manually start the epic-wide stack PR monitor for an epic whose first task's PR is already open, when it was not auto-started.
argument-hint: <epic key, e.g. ADR-369>
---

## Request

$ARGUMENTS

## Steps

### 1 — Determine epic id

Extract the `[A-Z]+-\d+` epic key from the arguments. If no match is found, tell the user:

> Please provide an epic key (e.g. ADR-369).

Then stop.

### 2 — Spawn the monitor

This command's only job is spawning `dev-team:monitor-stack` in its own fresh, isolated
worktree — the manual fallback for when `concurrent-orchestrate`'s auto-start never happened
(e.g. its own session was interrupted before the epic's first task reached hand-off). A bare
skill invocation from this session would get no isolation at all, so the spawn itself is what
gives the monitor the same isolation guarantee the auto-started path has.

```
Agent(
  subagent_type: "claude",
  isolation: "worktree",
  prompt: "Invoke the `monitor-stack` skill with arguments:
--work-item-id <epic-id>"
)
```

Then stop.
