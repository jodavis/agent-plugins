---
name: work-with-pr
user-invocable: false
description: >
  Use when you are working with an existing GitHub PR.
  Covers reading PR details and diffs, posting inline comments, managing pending reviews, resolving threads, and requesting human review.
argument-hint: <pr_url>
---

Use this skill when:
- You are working with an existing GitHub PR
- You need to read PR details, comments, or diffs
- You need to post a review or inline comments
- You need to resolve review threads

## General guidance

When executing a `gh` or `git` command, never prepend a `cd` to the directory
onto the command. Command safety scanners see this as a risk and prompt for
permission, breaking autonomy.

## Extracting PR details from a URL

Given a PR URL of the form `https://github.com/<owner>/<repo>/pull/<number>`:
- `owner` — the GitHub user or org
- `repo` — the repository name
- `pullNumber` — the integer after `/pull/`

## Reading the PR

**Fetch the diff:**
```
mcp__plugin_github_github__pull_request_read(method="get_diff", owner=<owner>, repo=<repo>, pullNumber=<number>)
```

**Fetch review threads (for sign-off):**
```
mcp__plugin_github_github__pull_request_read(method="get_review_comments", owner=<owner>, repo=<repo>, pullNumber=<number>)
```

Each thread has:
- `id` — the node ID (`PRRT_...`) used to resolve the thread
- `isResolved` — whether the thread is already resolved
- `comments.nodes[0]` — the first comment: `body`, `path`, and numeric `id`

## Posting a review

Gather all inline issues before creating the pending review — it does not appear to reviewers until it is submitted.

**1. Create a pending review:**
```
mcp__plugin_github_github__pull_request_review_write(method="create", owner=<owner>, repo=<repo>, pullNumber=<number>)
```

**2. Add each inline comment** (use source file line numbers, not diff positions):
```
mcp__plugin_github_github__add_comment_to_pending_review(owner=<owner>, repo=<repo>, pullNumber=<number>, path=<file>, line=<line>, side="RIGHT", subjectType="LINE", body=<comment>)
```

Get the configured attribution line once (via the `message-attribution` skill) before gathering
inline issues, then append it to each inline comment's `body` in this step — every inline
comment carries it, not just the overall review summary.

**3. Submit the pending review** — use `event: COMMENT`, not `APPROVE` or `REQUEST_CHANGES` (GitHub rejects those when reviewer and PR author share the same account):
```
mcp__plugin_github_github__pull_request_review_write(method="submit_pending", owner=<owner>, repo=<repo>, pullNumber=<number>, body=<overall summary>, event="COMMENT")
```

Append the same attribution line to step 3's `body` argument too.

## Responding to and resolving threads

**Reply to an existing thread** (use the numeric comment ID of the thread's first comment):
```
mcp__plugin_github_github__add_reply_to_pull_request_comment(owner=<owner>, repo=<repo>, pullNumber=<number>, commentId=<numeric id>, body=<reply>)
```

Before this call, use the `message-attribution` skill to get the configured attribution line, if
any, and append it to the `body` argument.

**Resolve a thread** (use the node ID `PRRT_...`):
```
mcp__plugin_github_github__pull_request_review_write(method="resolve_thread", owner=<owner>, repo=<repo>, pullNumber=<number>, threadId=<PRRT_... node ID>)
```

## Hand-off operations

These three operations are bare, mechanical, and independently callable — each is invoked on
its own from a plain-language instruction (e.g. by `run-hook-instructions`, following a project's
configured `after-signoff-approved` instructions). None of them reads an environment variable; the
reviewer's or assignee's identity is always a literal value the calling instruction supplies.

### convert-to-ready

Convert the PR from draft to Ready for Review:
```
mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, draft=false)
```

### request-review

Given a GitHub username (supplied by the caller), request their review on the PR:
```
mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, reviewers=["<github-username>"])
```

### assign-issue

Given a Jira issue key and a reviewer identity (name or email, supplied by the caller), assign
the Jira issue to that reviewer using `work-with-Jira-tasks`:
1. Use the `lookupJiraAccountId` operation to resolve the identity to a Jira account ID.
2. Use the `editJiraIssue` operation to set the issue's assignee to that account ID.
