---
name: work-with-Jira-tasks
user-invocable: false
description: >
  Use when you are working with a Jira task.
  Provides tool names and patterns for reading and updating Jira issues via MCP.
---

Use this skill when:
- You need to read details from a Jira issue
- You need to add a comment, update fields, or transition a Jira issue
- Another skill tells you to use a Jira operation "from `work-with-Jira-tasks`"

## Finding the right tool

The exact MCP tool name for each Jira operation depends on which Atlassian/Jira MCP server
happens to be connected in the current environment — for example a server literally named
`jira` exposes tools as `mcp__jira__<suffix>`, while the `claude.ai Atlassian Rovo` connector
exposes the same operations as `mcp__claude_ai_Atlassian_Rovo__<suffix>`. Never hardcode a
specific prefix. Instead, every time you need one of the operations below:

1. Call `ToolSearch` with the operation's suffix (from the table below) as the query, e.g.
   `ToolSearch(query="editJiraIssue")`.
2. Confirm the matched tool's full name contains `Jira` or `Atlassian` (case-insensitive)
   before calling it — this guards against an unrelated tool that happens to share a suffix.
3. Call the matched tool with the arguments described for that operation.

If no tool matches, no Jira/Atlassian MCP server is connected in this environment — stop and
report that rather than guessing a tool name.

## Operations

| Operation | Tool suffix | What it does |
|---|---|---|
| Read issue | `getJiraIssue` | Retrieve issue fields: summary, description, status, parent/epic, assignee |
| Add a comment | `addCommentToJiraIssue` | Post a comment on the issue |
| Edit fields | `editJiraIssue` | Update fields such as assignee or description |
| List available transitions | `getTransitionsForJiraIssue` | List the statuses the issue can transition to |
| Transition to a new status | `transitionJiraIssue` | Move the issue to a new status |
| Look up account ID by email | `lookupJiraAccountId` | Resolve a user's Jira account ID (and linked GitHub username, if any) from their email |
| Get authenticated user info | `atlassianUserInfo` | Return the identity of the currently authenticated Atlassian user |
| Link two issues | `createIssueLink` | Create a typed link (e.g. `Blocks`) between two issues |

Other skills should reference these operations by name (e.g. "the `editJiraIssue` operation
from `work-with-Jira-tasks`") rather than hardcoding a `mcp__<prefix>__<suffix>` tool name
directly.

### Attribution

Before calling `addCommentToJiraIssue`, or `editJiraIssue` to write/replace a `description`
field, use the `message-attribution` skill to get the configured attribution line, if any, and
append it to the comment body or description text.

### Reading a Jira issue

Use the `getJiraIssue` operation with the issue key (e.g. `PROJ-228`) to retrieve the issue
fields, including summary, description, status, parent/epic, and assignee.

### Recording a "depends on" relationship

To record that one task-work-item depends on another, use the `createIssueLink` operation with
the `Blocks` link type: the dependency is the blocker, the dependent task is the blocked issue.
Jira's link direction is named from the blocker's side, so set `inwardIssue` to the dependency's
key and `outwardIssue` to the dependent task's key (e.g. task `PROJ-230` depends on `PROJ-228` →
`inwardIssue: PROJ-228`, `outwardIssue: PROJ-230`, `type: Blocks`).

## Finding the parent feature-work-item

When you need the parent feature-work-item's key, use the `getJiraIssue` operation with the
task key and look for a `parent` or `epic` field in the returned issue. Extract its key (e.g.
`PROJ-200`). If the field is absent, the task has no parent feature-work-item.
