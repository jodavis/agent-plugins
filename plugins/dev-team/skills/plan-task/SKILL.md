---
name: plan-task
user-invocable: false
description: >
  Use when making a plan to implement a task-work-item.
  Identifies the work item, reads the spec, spawns parallel researcher agents to gather architecture, source, and external knowledge, and produces a task brief.
---

Use this skill when:
- A user asks to make a plan to implement a task
- You need to produce a task brief for a work item

You need to identify a task-work-item and learn the architecture from documentation in this repo, then you are researching the work item and writing a task brief for the work item.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the spec section

Use the `read-spec-section` skill with the `work-item-id` to get the **task context** (the spec section describing this work item).

### 3 — Spawn parallel researcher agents

Spawn three `dev-team:researcher` agents in parallel. Pass each one the full task context from step 2.

**Agent 1 — Architecture docs:**
> Use the `find-repo-documentation` skill to discover all architecture docs in the repo. Read the ones relevant to this task and return a summary of what each says about the areas this task will touch.
>
> Task context:
> `<paste task context here>`

**Agent 2 — Source code patterns:**
> Use the `research-sources` skill to find and read the source files most relevant to this task. Focus on existing interfaces, utilities, and patterns the implementer should use or extend.
>
> Task context:
> `<paste task context here>`

**Agent 3 — External best practices:**
> Use the `research-learn` skill to research any frameworks, libraries, or patterns this task will use that are not fully covered by local docs. Return findings with source links.
>
> Task context:
> `<paste task context here>`

Wait for all three agents to complete and collect their output.

### 4 — Write the task brief

Use the `write-task-brief` skill, providing:
- The `work-item-id`
- The spec section (task context from step 2)
- The combined research findings from all three agents (step 3)

Return the task brief as prose.
