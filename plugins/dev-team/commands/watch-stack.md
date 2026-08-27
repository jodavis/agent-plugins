---
description: Manually start the epic-wide stack PR monitor for the stack already checked out in this worktree.
---

## Steps

### 1 — Invoke the monitor directly, in this session

This command only ever operates on the stack already checked out in this worktree — the only
entry point is being on the stack already; not being on any stack is a hard stop (`monitor-prs`
step 2b), not a fallback to an argument. This command is always a direct, user-initiated action —
unlike `concurrent-orchestrate`'s own auto-start (which spawns `monitor-prs` in a fresh,
isolated worktree because that orchestrator has other pipeline work of its own to protect), there
is no other pipeline running in this session for the monitor to collide with, and no reason to
force it into a worktree you may already be sitting in yourself. Invoke the skill directly — no
`Agent` spawn, no `isolation: "worktree"`, and no arguments:

Invoke the `monitor-prs` skill with no arguments.

This session now *is* the monitor for as long as it runs — that's expected; this command has no
other orchestration duty to get back to.
