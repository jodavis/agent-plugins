---
description: Run the dev-team implementation pipeline for a Jira task, an "up to" dependency target, or an explicit list of tasks.
argument-hint: <Jira task key, "up to <key>", or a comma/"and"-separated list>
---

## Request

$ARGUMENTS

## Steps

### 1 — Parse the argument

Check the arguments, in order:

1. **"up to" form** — the case-insensitive literal phrase `up to <key>` (e.g. `up to ADR-310`,
   `Up To adr-310`). Extract `<key>` (the `[A-Z]+-\d+` pattern immediately following "up to").
   Go to step 3, passing `--target-mode up-to --target <key>`.
2. **Explicit list form** — otherwise, extract every `[A-Z]+-\d+` occurrence anywhere in the
   arguments:
   - **Two or more matches**, however separated (commas, the word "and", or both — e.g.
     `ADR-310, ADR-311, and ADR-312`): go to step 3, passing
     `--target-mode list --target <key1,key2,...>` (comma-joined, in the order they appeared).
   - **Exactly one match**: a single work item, unchanged from today's behavior — go to step 2.
   - **No match**: tell the user:

     > Please provide a Jira task key (e.g. ADR-123), an "up to" target (e.g. "up to ADR-123"),
     > or an explicit list (e.g. "ADR-123, ADR-124, and ADR-125").

     Then stop.

### 2 — Run the single-task workflow

Invoke the `workflow-orchestrate` skill with arguments:
`--work-item-id <work-item-id> --workflow implement-task-plan --research-skill plan-task`

### 3 — Run the concurrent workflow

Invoke the `concurrent-orchestrate` skill with arguments:
`--target-mode <up-to|list> --target <key, or comma-separated keys>`
