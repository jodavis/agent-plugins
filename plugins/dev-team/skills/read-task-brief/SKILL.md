---
name: read-task-brief
user-invocable: false
---

## Arguments

- `work-item-id` — the task to read a brief for.
- `--tolerate-missing-brief` (optional) — when passed, step 2's "no brief found" case returns
  empty content instead of stopping (see step 2 below). Only pass this when the caller has its
  own fallback for building context without a brief (e.g. `fix-pr`, #233) — every other caller
  should omit it, since for them a missing brief genuinely does mean the plan step was skipped.

## Steps

### 1 — Resolve the context file and confirm the working branch

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file,
including its "Confirming the working branch" step — this skill is about to read/write repository
files in the next steps.

### 2 — Read the task brief

Read the context file. Locate the `<!-- section:Researcher Brief -->` sentinel and extract all content that follows it until the next `<!-- section:` marker or end of file.

If no task brief section is found:

- **`--tolerate-missing-brief` was not passed:** stop and report:

  > No task brief was found in the context file for `<work-item-id>`. Run the plan step before implementing.

- **`--tolerate-missing-brief` was passed:** return empty content as the **task brief** instead of stopping — do not report anything about it here; the caller already knows to expect this and has its own fallback.

Otherwise, return the extracted content as the **task brief**.
