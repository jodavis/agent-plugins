---
name: read-task-brief
user-invocable: false
---

## Arguments

- `work-item-id` — the task to read a brief for.

## Steps

### 1 — Resolve the context file and confirm the working branch

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file,
including its "Confirming the working branch" step — this skill is about to read/write repository
files in the next steps.

### 2 — Read the task brief

Read the context file. Locate the `<!-- section:Researcher Brief -->` sentinel and extract all content that follows it until the next `<!-- section:` marker or end of file.

Return the extracted content as the **task brief** — or empty content if no task brief section
is found. This skill never stops or reports an error on a missing brief itself: whether that's
expected (e.g. `fix-pr`, #233, has its own fallback for building context without one) or a real
problem (e.g. the plan step was skipped) depends entirely on what the caller needs, so it's the
caller's own job to check the returned content and decide — not this skill's.
