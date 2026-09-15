---
name: review-sign-off
user-invocable: false
description: >
  Use when performing a sign-off review after a developer has addressed prior review comments.
  Checks each prior thread for resolution, scans modified files for new issues, and submits a sign-off review.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are performing a sign-off review after a developer has addressed prior code review comments

You are working with an existing PR, reading from a workflow context file, learning the architecture from documents in this repo, reviewing code changes, and creating a PR review.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief from the context file and ensure the working branch is set up.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates. These are the standards against which you will evaluate the code.

### 4 — Note recent changes

Check what has changed since the previous review pass:

```bash
git log --oneline -5
```

### 5 — Fetch prior review threads

Use the `work-with-pr` skill to fetch all review threads from the PR at `pr_url`.

For each thread where `isResolved` is `false`, note:
- What was the original issue (from the first comment body)?
- What file was it on?
- Has that file been modified since the comment was posted?

### 6 — Check each thread for resolution

Review each unresolved thread and determine the outcome. Do not create a pending review yet — collect all findings first.

- **Addressed satisfactorily:** the problem no longer exists in the code. Mark for resolution.
- **Developer disagreed (posted rationale):** read the rationale.
  - **Accept:** mark for resolution with a reply acknowledging it.
  - **Reject:** note a follow-up reply restating the requirement. Leave unresolved.
- **Partially addressed:** note a follow-up comment explaining what still needs to be done. Leave unresolved.
- **Not addressed:** note a follow-up comment restating what is needed and why. Leave unresolved.

### 7 — Scan modified files for new issues

Use the `review-guidelines` skill to evaluate only the files modified since the last review push. Do not re-review unmodified code.

### 8 — Post the sign-off review

Use the `work-with-pr` skill to:

1. Create a pending review
2. For each thread marked for resolution in step 6: resolve it (and add any reply noted)
3. For each thread with a follow-up reply noted in step 6: add the reply, leave unresolved
4. For each Priority 1–4 issue found in step 7: add an inline comment
5. Submit the pending review with an overall summary using `event: COMMENT`

Posting this review to the live PR is the expected, required completion of this skill. It is
always submitted as `event: COMMENT` — never `APPROVE` — specifically because pipeline PRs and
the account posting the review share the same identity, and GitHub's own semantics for a
self-authored `APPROVE`/`REQUEST_CHANGES` review don't apply cleanly here. Do not substitute a
different review event, and do not stop to ask whether you should post it.

**Sign-off decision:** use `"approved"` if all threads are resolved and no new Priority 1–4 issues were found; `"changes_requested"` otherwise.

### 9 — Output

Compose a concise summary:
- For each prior thread: whether it was resolved or still needs work
- Any new issues found in the modified files

Then compose the following JSON object as the very last line, as a bare JSON object with no code
block or trailing text:

{"status": "approved|changes_requested", "pr_url": "https://github.com/..."}

Use the `write-scratch-deliverable` skill to write the summary and JSON object together in place
of returning them as chat text.
