---
name: plan-task
user-invocable: false
description: >
  Use when making a plan to implement a task-work-item.
  Identifies the work item, reads the spec, researches architecture, source, and external knowledge, and produces a task brief.
---

Use this skill when:
- A user asks to make a plan to implement a task
- You need to produce a task brief for a work item

You need to identify a task-work-item and learn the architecture from documentation in this repo, then you are researching the work item and writing a task brief for the work item.

## Steps

### 1 — Identify the work item

Use the `identify-project-work-items` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the spec section

Use the `read-dev-spec-section` skill with the `work-item-id` to get the **task context** (the spec section describing this work item).

### 3 — Research the task from three angles

**Do this yourself, in your own turn, using the `Skill` tool — do not spawn sub-agents for this
step.** This skill runs as (or under) a `dev-team:researcher` agent, and that agent's own tool
list has no `Agent`/`Task` tool, so it cannot spawn further agents of any kind, including more
copies of itself. Invoke each of the following three skills in turn, passing the full task
context from step 2 to each:

1. `find-repo-documentation` — discover all architecture docs in the repo. Read the ones
   relevant to this task and note a summary of what each says about the areas this task will
   touch.
2. `research-sources` — find and read the source files most relevant to this task. Focus on
   existing interfaces, utilities, and patterns the implementer should use or extend.
3. `research-learn` — research any frameworks, libraries, or patterns this task will use that
   are not fully covered by local docs. Note findings with source links.

Collect all three outputs before moving on.

### 4 — Write the task brief

Use the `write-task-brief` skill, providing:
- The `work-item-id`
- The spec section (task context from step 2)
- The combined research findings from all three research passes (step 3)

Return the task brief as prose.
