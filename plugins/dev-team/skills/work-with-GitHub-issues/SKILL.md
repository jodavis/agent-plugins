---
name: work-with-github-issues
user-invocable: false
description: >
  Use when you are working with a GitHub issue.
  Provides tool names and CLI commands for reading and updating GitHub issues.
---

Use this skill when:
- You need to read details from a GitHub issue
- You need to add a comment or update a GitHub issue

## General guidance

When executing a `gh` or `git` command, never prepend a `cd` to the directory
onto the command. Command safety scanners see this as a risk and prompt for
permission, breaking autonomy.

## Reading an issue

Use `mcp__plugin_github_github__issue_read` with `owner`, `repo`, and `issue_number`. Alternatively use the `gh` CLI:

```bash
gh issue view <issue-number>
```

## Common operations

| Operation | Tool / CLI |
|---|---|
| Read issue | `mcp__plugin_github_github__issue_read` or `gh issue view <n>` |
| Add a comment | `mcp__plugin_github_github__add_issue_comment` or `gh issue comment <n> --body "..."` |
| Write/update issue | `mcp__plugin_github_github__issue_write` |
| Search issues | `mcp__plugin_github_github__search_issues` |
| List issues | `mcp__plugin_github_github__list_issues` |

## Issue number

GitHub issues use the `#42` notation on GitHub, but the canonical `work-item-id` for branches and file paths uses the `Issue-42` format. Strip the `Issue-` prefix and `#` to get the numeric ID for tool calls.
