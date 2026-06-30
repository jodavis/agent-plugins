---
name: review
user-invocable: false
description: >
  Use when performing a first-pass code review for a work item.
  Reads the task brief and architecture docs, evaluates the PR diff against requirements and quality criteria, and posts a GitHub PR review.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are performing the first-pass code review for a work item

You are working with an existing PR, reading from a workflow context file, learning the architecture from documents in this repo, reviewing code changes, and creating a PR review.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief and ensure the working branch is set up. Extract the **exit criteria** — these are the explicit list of things the implementation must satisfy. You will check each one during review.

Verify that `pr_url` is set in the context file. If it is empty, report an error and stop:

> `pr_url` is not set in the context file for `<work-item-id>`. A PR must exist before reviewing.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates. These are the standards against which you will evaluate the code.

### 4 — Read relevant architecture docs

Use the `find-repo-documentation` skill with the task context to discover and read the architecture docs relevant to this change.

### 5 — Read the PR diff

Use the `work-with-pr` skill to fetch the PR diff from `pr_url`. Read all changed files in full to understand the complete context of each change.

### 6 — Review the changes

Use the `review-guidelines` skill to evaluate the diff. Collect all issues — file path, line number, and description — before posting anything.

Do not create a pending review yet. Review the full diff first so the pending review is created and submitted as a single batch.

### 7 — Post the review

Use the `work-with-pr` skill to:
1. Create a pending review
2. Add one inline comment per Priority 1–4 issue found in step 6
3. Submit the pending review with an overall summary

### 8 — Output

Write a concise plain-text summary of all issues found — one bullet per issue, Priority 1–4 first, style issues last.

Then output the following JSON object as the very last line of your response. Write it as a bare JSON object — do not wrap it in a code block or add any text after it:

{"status": "approved|changes_requested", "pr_url": "https://github.com/..."}

Use `"approved"` if no Priority 1–4 issues were found; `"changes_requested"` otherwise. Always include the PR URL.
