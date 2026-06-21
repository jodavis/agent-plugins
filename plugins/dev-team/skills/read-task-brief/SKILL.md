---
name: read-task-brief
description: >
  Use when you need to read the task brief for a work item.
  Resolves the context file, ensures the working branch, and extracts the task brief section.
argument-hint: <work-item-id>
---

Use this skill when:
- You need to read the task brief before implementing a work item

## Steps

### 1 — Resolve the context file

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file.

### 2 — Ensure the working branch

Use the `ensure-working-branch` skill with the `work-item-id` and the resolved context file path.

### 3 — Read the task brief

Read the context file. Locate the `<!-- section:task-brief -->` sentinel and extract all content that follows it until the next `<!-- section:` marker or end of file.

If no task brief section is found, stop and report:

> No task brief was found in the context file for `<work-item-id>`. Run the plan step before implementing.

Return the extracted content as the **task brief**.
