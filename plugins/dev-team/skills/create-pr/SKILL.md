---
name: create-pr
user-invocable: false
description: >
  Use when creating a new pull request in GitHub.
  Determines repo coordinates from the git remote, creates a draft PR with a structured body, and returns the PR URL.
argument-hint: <work-item-id> <working-branch> <base-branch> <task-brief>
---

Use this skill when:
- You are creating a new pull request in GitHub

## Steps

### 1 — Determine repo coordinates

Parse `owner` and `repo` from the remote URL:

```bash
git remote get-url origin
```

Extract from formats like `https://github.com/owner/repo.git` or `git@github.com:owner/repo.git`.

### 2 — Create the draft PR

Use `mcp__plugin_github_github__create_pull_request` with:

- `owner` and `repo` from step 1
- `head`: the working branch name
- `base`: the base branch name
- `draft`: `true`
- `title`: `"<work-item-id>: <concise one-line description of what the implementation delivers>"`
- `body`: A well-structured description with these sections:
  - **Work item:** `<work-item-id>` with a one-sentence summary of what the task required
  - **Changes:** A bullet list drawn from the task brief or work summary — one bullet per logical change (new file, modified interface, new test scenario, etc.)
  - **Design decisions:** Any non-obvious choices made during implementation that a reviewer needs context for (omit if there are none)
  - If the work item ID matches `Issue-\d+` (a GitHub issue), append as the final line: `Closes #<number>` (e.g. `Issue-123` → `Closes #123`)

The PR title and body are read by human reviewers — write them clearly and precisely.

### 3 — Return the PR URL

Return the URL of the newly created PR.
