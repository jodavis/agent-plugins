---
name: final-sign-off
user-invocable: false
description: >
  Use when handing off an approved PR to a human reviewer.
  Converts the PR from draft to ready, assigns the Jira issue, and requests a GitHub review.
argument-hint: <pr_url> <work-item-id>
---

Use this skill when:
- A review has been approved and the PR is ready for human review
- You need to hand off from agent review to human review

You are working with an existing PR and updating the task work item to reflect the hand-off.

## Steps

### 1 — Convert PR to ready for review

Use the `work-with-pr` skill to convert the PR from draft to Ready for Review:

```
mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, draft=false)
```

### 2 — Look up the human reviewer

Call `mcp__jira__lookupJiraAccountId` with `$REVIEW_ASSIGNEE_EMAIL` to get the human reviewer's Jira account ID and GitHub username.

### 3 — Assign the Jira issue

Call `mcp__jira__editJiraIssue` to assign the Jira issue to the reviewer's account ID.

### 4 — Request a GitHub review

```
mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, reviewers=["<github-username>"])
```

### 5 — Add a Jira comment

Call `mcp__jira__addCommentToJiraIssue` with the message:

> PR ready for human review — reviewer requested on GitHub.

### 6 — Report completion

Output a one-line confirmation as your final output, e.g.:

> Handed off `<pr_url>` to `<github-username>` for human review; Jira issue assigned.
