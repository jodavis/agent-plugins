---
name: identify-project-work-items
user-invocable: false
description: >
  Identifies the active work item from user input or conversation context.
  Use this skill when you need to know the work-item-id or work-item-type.
---

**Extension point skill** — configure this via `get-project-configuration`'s `work-tracking`
section (preferred). Full-file override remains available as an escape hatch: place a `SKILL.md`
in `.claude/skills/identify-project-work-items/` to replace this skill's process entirely.

Use this skill when:
- Another skill requires a `work-item-id` and `work-item-type`

Do NOT use this skill when:
- You already know the `work-item-id` and `work-item-type` that is under active development

## Configured behavior

Invoke `get-project-configuration` and read `work-tracking`.

**If `work-tracking` is `null` or an empty map, this project has no issue tracker configured —
skip straight to Default behavior below** (ask the user directly; do not guess a provider).

Otherwise, for each `(provider-name, provider-config)` pair in `work-tracking`, try to match the
user's input or conversation context against that provider's `issue-key-pattern` and
`recognize-patterns`. On a match, output `work-item-id` (the canonical id), `work-item-type` (=
`provider-name`), and `numeric-id` (extracted from the match). If nothing matches any configured
provider, fall through to Default behavior.

## Default behavior (no project override, or no match against configured patterns)

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
