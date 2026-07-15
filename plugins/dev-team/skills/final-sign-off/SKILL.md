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

Use the `lookupJiraAccountId` operation from `work-with-Jira-tasks` with `$REVIEW_ASSIGNEE_EMAIL` to get the human reviewer's Jira account ID and GitHub username.

### 3 — Assign the Jira issue

Use the `editJiraIssue` operation from `work-with-Jira-tasks` to assign the Jira issue to the reviewer's account ID.

### 4 — Request a GitHub review

```
mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, reviewers=["<github-username>"])
```

### 5 — Check for a Method marker to mention

Invoke `get-project-configuration` and read `documentation`. Substitute `work-item-id` into
`documentation.specs.search` and run it as a shell command to locate the spec (pattern:
`find-repo-documentation`'s use of `documentation.architecture.search`). If no spec is found,
skip this step silently — no error, no user prompt.

If a spec is found, read it and check for a `> [!NOTE]` / `> **Method:**` marker (defined by
`playbook-contract`). If present, note that the Jira comment in the next step should mention
`/harvest` is available once the method is judged proven. Never invoke `harvest-playbook`
here — the mention is passive only.

### 6 — Add a Jira comment

Use the `addCommentToJiraIssue` operation from `work-with-Jira-tasks` with the message:

> PR ready for human review — reviewer requested on GitHub.

If step 5 found a Method marker in the spec, append a sentence to the comment:

> The spec contains a Method marker — once this method is judged proven, `/harvest` is available
> to capture it as a playbook.

### 7 — Report completion

Output a one-line confirmation as your final output, e.g.:

> Handed off `<pr_url>` to `<github-username>` for human review; Jira issue assigned.
