---
description: Manually start the epic-wide stack PR monitor — for the stack already checked out in this worktree, or (given an epic key) for an epic whose first task's PR is open but wasn't auto-started.
argument-hint: [epic key, e.g. ADR-369]
---

## Request

$ARGUMENTS

## Steps

### 1 — Determine epic id, if given

Extract an `[A-Z]+-\d+` epic key from the arguments, if present. This argument is only needed
when you are **not** already sitting in the target stack's own worktree — e.g. `monitor-stack`
was never auto-started for this epic and you're invoking this command from somewhere else
entirely. If you're already checked out on one of the stack's own branches, omit it:
`monitor-stack` derives the epic from the current worktree instead (its own step 2).

### 2 — Invoke the monitor directly, in this session

This command is always a direct, user-initiated action — unlike `concurrent-orchestrate`'s own
auto-start (which spawns `monitor-stack` in a fresh, isolated worktree because that orchestrator
has other pipeline work of its own to protect), there is no other pipeline running in this
session for the monitor to collide with, and no reason to force it into a worktree you may
already be sitting in yourself. Invoke the skill directly — no `Agent` spawn, no
`isolation: "worktree"`:

Invoke the `monitor-stack` skill with arguments:
--work-item-id <epic-id, if step 1 found one; omit this flag entirely otherwise>

This session now *is* the monitor for as long as it runs — that's expected; this command has no
other orchestration duty to get back to.
