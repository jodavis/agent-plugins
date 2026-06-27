---
name: identify-project-work-items
description: >
  Identifies the active work item from user input or conversation context.
  Use this skill when you need to know the work-item-id or work-item-type.
---

**Extension point skill** — projects must override this skill with their own work item patterns.
Place a `SKILL.md` in `.claude/skills/identify-project-work-items/` to define how work items are
identified for your tracker (Jira, GitHub Issues, Linear, etc.).

Use this skill when:
- Another skill requires a `work-item-id` and `work-item-type`

Do NOT use this skill when:
- You already know the `work-item-id` and `work-item-type` that is under active development

## Default behavior (no project override)

Ask the user:

> What work item are you working on?

Derive a canonical `work-item-id` from their response. Use the format `<PREFIX>-<NUMBER>` (e.g.
`PROJ-123`) for tracker issues, or `Issue-<NUMBER>` for GitHub issues.

## Output

Return these fields as a short structured block:

```
work-item-id: <id>
work-item-type: <jira|github|other>
numeric-id: <number>
```
