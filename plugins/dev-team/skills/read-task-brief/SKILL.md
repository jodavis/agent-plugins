---
name: read-task-brief
user-invocable: false
---

## Steps

### 1 — Resolve the context file and confirm the working branch

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file,
including its "Confirming the working branch" step — this skill is about to read/write repository
files in the next steps.

### 2 — Read the task brief

Read the context file. Locate the `<!-- section:Researcher Brief -->` sentinel and extract all content that follows it until the next `<!-- section:` marker or end of file.

If no task brief section is found, stop and report:

> No task brief was found in the context file for `<work-item-id>`. Run the plan step before implementing.

Return the extracted content as the **task brief**.
