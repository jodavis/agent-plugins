---
name: identify-project-work-items
description: >
  Defines the work item patterns for this project.
  Use this skill when you need to know the active work-item-id or work-item-type, which can be used to create branches, look up specs, or access work item information online.
---

# Work item tracking for AdaptiveRemote and related projects

Use this skill when:
- Another skill requires `work-item-id` in `ADR-###` or `Issue-###` format

Do NOT use this skill when:
- You already know the `work-item-id` and `work-item-type` that is under active development

This project uses Jira for work item planning and GitHub issues for tracking bugs and public discussions. The project prefix for all Jira work items is `ADR-`.


## Patterns for recognizing work items

Look for the following patterns in user input or previous discussion to identify the work item that is under active development.

| Example patterns | Canonical `work-item-id` | `work-item-type` | `numeric-id` |
|---|---|---|---|
| ADR-123, Task 123, Epic 123, Jira 123 | `ADR-123` | `jira` | `123` |
| `#42`, `Issue 42`, `GitHub 42` | `Issue-42` | `github` | `42` |

Note: The canonical `work-item-id` is used by other skills to create git branch names and file paths. The `Issue-42` pattern is used for GitHub because the GitHub standard `#42` would not be valid in those contexts.

## Output

Return these fields as a short structured block:

```
work-item-id: ADR-123
work-item-type: jira
numeric-id: 123
```

If the input does not contain any matches for any known pattern, stop and ask: `What work item do you want to work on?`