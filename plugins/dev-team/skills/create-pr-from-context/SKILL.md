---
name: create-pr-from-context
user-invocable: false
description: >
  Use when creating a pull request for a work item using the workflow context file.
  Reads the context file, ensures the working branch, creates a PR, and writes the PR URL back to the context file.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are creating a pull request in GitHub for a work item and the task brief is in the workflow context file

You are reading from the context file, creating a new pull request in GitHub, and updating the context file.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief, ensure the working branch is set up, and retrieve the branch names from the context file.

### 3 — Check if PR already exists

If `pr_url` is already set in the context file, the PR has already been created. Output the PR URL and stop:

```json
{"pr_url": "<pr_url>"}
```

### 4 — Create the PR

Use the `create-pr` skill, providing the `work-item-id`, working branch, `base_branch` (from the
context file), and task brief content.

This task's branch is never registered into a `gh stack` at this point in the pipeline — that
only happens later, in `add-to-pr-stack`, once sign-off approves (see that skill's own intro).
`base_branch` (written by `ensure-working-branch`) is the single source of truth for this PR's
base regardless of whether the task is part of a tracked epic at all: either the epic's feature
branch, or the working branch of whichever declared dependency sorts latest in the epic's
document order. This is what closes Issue-129 (PRs opening against the wrong base) — there is no
separate stack-relative code path here to drift out of sync with it.

### 5 — Update the context file

Use the `use-context-file` skill to write the returned PR URL to the `pr_url` frontmatter field in the context file.

Use the `write-scratch-deliverable` skill to write the following in place of returning it as chat
text:

```json
{"pr_url": "https://github.com/..."}
```
