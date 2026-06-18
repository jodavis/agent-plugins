---
description: Create a draft GitHub pull request for a completed work item. Determines the correct base branch, writes a developer-authored PR body, and creates the PR as a draft. Idempotent — does nothing if the PR already exists.
argument-hint: <work-item-id | context-file>
user-invocable: false
---

## Steps

### 0 - Prepare

Determine the work-item-id for the active task.

Ensure the working repository and task context file are in a clean, ready-to-work state.

### 1 — Check if PR already exists

If the context file already contains `pr_url`, the PR has already been created. Output the following JSON and
stop:

```json
{"pr_url": "<pr_url>"}
```

### 2 — Determine the base branch and repo coordinates

The working branch name and base branch name can be found in the context file. 

Parse owner and repo from the remote URL:
```bash
git remote get-url origin
```
Extract `owner` and `repo` from formats like `https://github.com/owner/repo.git`
or `git@github.com:owner/repo.git`.

### 3 — Create the draft PR

Use `mcp__plugin_github_github__create_pull_request` with:

- `owner` and `repo` from step 2
- `head`: the current branch name from step 2
- `base`: the base branch from step 2
- `draft`: `true`
- `title`: `"<work-item-id>: <concise one-line description of what the implementation delivers>"`
- `body`: A well-structured description with these sections:
  - **Work item:** `<work-item-id>` with a one-sentence summary of what the task required
  - **Changes:** A bullet list drawn from the work summaries — one bullet per logical change
    (new file, modified interface, new test scenario, etc.)
  - **Design decisions:** Any non-obvious choices made during implementation that a reviewer
    needs context for (omit if there are none)
  - If the work item ID matches `Issue-\d+` (a GitHub issue), append a closing reference as
    the final line of the body: `Closes #<number>` (e.g. `Issue-123` → `Closes #123`). This
    links the PR to the issue under "Development" and closes the issue automatically on merge.

The PR title and body are read by human reviewers — write them clearly and precisely.

### 4 — Output

Output the PR URL as the final JSON line:

{"pr_url": "https://github.com/..."}
