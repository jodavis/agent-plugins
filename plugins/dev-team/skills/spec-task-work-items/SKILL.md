---
name: spec-task-work-items
user-invocable: false
description: >
  Use when you are writing a new spec or a new part of an existing spec.
  Updates project work items with summaries after the spec is finalized.
argument-hint: <work-item-id> <spec-path>
---

**Extension point skill** — projects should override this skill to integrate with their work item
tracker (Jira, GitHub Issues, Linear, etc.). Place a `SKILL.md` in
`.claude/skills/spec-task-work-items/` to define how work items are updated after a spec is
finalized.

Use this skill when:
- You are writing a new spec or a new part of an existing spec
- The spec is finalized and project work items should reflect the decisions

## Default behavior (no project override)

No work item integration is configured for this project.

Output: `No work item integration configured; skipping work item updates.`
