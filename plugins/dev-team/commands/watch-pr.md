---
description: Manually start a lightweight monitor for one or more explicit PRs that aren't part of (or aren't known to be part of) a gh stack — no gh stack involvement.
argument-hint: <PR#> [PR#...]
---

## Request

$ARGUMENTS

## Steps

### 1 — Determine PR numbers

Extract one or more PR numbers from the arguments (bare integers, or `#123`/PR URLs — strip to
the bare number either way). If none are found, tell the user:

> Please provide one or more PR numbers (e.g. `/watch-pr 123` or `/watch-pr 123 124`).

Then stop.

### 2 — Invoke the monitor directly, in this session

Like `/watch-stack`, this command is always a direct, user-initiated action — there is no other
pipeline running in this session for the monitor to collide with, and no `concurrent-orchestrate`
auto-start equivalent for PR mode. Invoke the skill directly — no `Agent` spawn, no
`isolation: "worktree"`:

Invoke the `monitor-prs` skill with arguments:
--pr-numbers <comma-separated PR numbers from step 1>

This session now *is* the monitor for as long as it runs — that's expected; this command has no
other orchestration duty to get back to. Use `/watch-stack` instead if these PRs are part of a
`gh stack` you want rebase-conflict handling for.
