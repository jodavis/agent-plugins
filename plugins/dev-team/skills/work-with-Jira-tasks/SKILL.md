---
name: work-with-Jira-tasks
description: >
  Use when you are working with a Jira task.
  Provides tool names and patterns for reading and updating Jira issues via MCP.
---

Use this skill when:
- You need to read details from a Jira issue
- You need to add a comment, update fields, or transition a Jira issue

## Reading a Jira issue

Call `mcp__jira__getJiraIssue` with the issue key (e.g. `PROJ-228`) to retrieve the issue fields, including summary, description, status, parent/epic, and assignee.

## Common operations

| Operation | Tool |
|---|---|
| Read issue | `mcp__jira__getJiraIssue` |
| Add a comment | `mcp__jira__addCommentToJiraIssue` |
| Edit fields (assignee, description, etc.) | `mcp__jira__editJiraIssue` |
| List available transitions | `mcp__jira__getTransitionsForJiraIssue` |
| Transition to a new status | `mcp__jira__transitionJiraIssue` |
| Look up a user account ID by email | `mcp__jira__lookupJiraAccountId` |

## Finding the parent Epic

When you need the parent Epic key, call `mcp__jira__getJiraIssue` with the task key and look for a `parent` or `epic` field in the returned issue. Extract its key (e.g. `PROJ-200`). If the field is absent, the task has no Epic parent.
