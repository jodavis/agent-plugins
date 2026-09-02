---
description: Run the dev-team fix pipeline for a GitHub issue.
argument-hint: <GitHub issue number, e.g. "#444" or "444">
---

## Request

$ARGUMENTS

## Steps

### 1 — Determine work item ID

Parse the GitHub issue number from the arguments (any `#\d+` or bare `\d+` pattern).
Convert it to the work item ID format: `Issue-<number>` (e.g. `#444` → `Issue-444`).
If no issue number is found, tell the user:

> Please provide a GitHub issue number (e.g. #444).

Then stop.

### 2 — Run the workflow

Invoke the `workflow-orchestrate` skill with arguments:
`--work-item-id <work-item-id> --workflow fix-issue-plan --script implement`
