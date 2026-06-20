---
name: write-task-brief
description: >
  Use when you are writing a task brief for a work item.
  Produces a structured implementation plan from a spec section and research findings.
argument-hint: <task-key> <spec-section> <research-findings>
---

Use this skill when:
- You have completed research for a work item and need to write the task brief

## Task brief format

Open with this exact heading (substitute the real task key):

```
# Implementation plan for <task-key>
```

The brief must include all of the following sections:

**Task title and description**
One sentence stating what the task accomplishes and why.

**Exit criteria**
Copy the exit criteria checklist from the spec section verbatim. If the spec uses Gherkin scenarios, include them.

**Key design decisions**
Decisions already made in the spec that directly constrain this task's implementation. Do not include decisions from other parts of the spec that don't affect this task.

**Files and interfaces to create or modify**
List each file by path. For each: whether it is new or modified, and one sentence on what changes. Call out existing utilities, base classes, or patterns the developer should reuse rather than reinvent — include file paths.

**Known ambiguities**
Concrete questions the developer may need answered before or during implementation. Only include genuine gaps — not rhetorical questions or things already resolved in the spec.
