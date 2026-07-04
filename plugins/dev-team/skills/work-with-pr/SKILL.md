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

**3. Submit the pending review** — use `event: COMMENT`, not `APPROVE` or `REQUEST_CHANGES` (GitHub rejects those when reviewer and PR author share the same account):
```
mcp__plugin_github_github__pull_request_review_write(method="submit_pending", owner=<owner>, repo=<repo>, pullNumber=<number>, body=<overall summary>, event="COMMENT")
```

## Responding to and resolving threads

**Reply to an existing thread** (use the numeric comment ID of the thread's first comment):
```
mcp__plugin_github_github__add_reply_to_pull_request_comment(owner=<owner>, repo=<repo>, pullNumber=<number>, commentId=<numeric id>, body=<reply>)
```

**Resolve a thread** (use the node ID `PRRT_...`):
```
mcp__plugin_github_github__pull_request_review_write(method="resolve_thread", owner=<owner>, repo=<repo>, pullNumber=<number>, threadId=<PRRT_... node ID>)
```

## Requesting human review (approved sign-off only)

When a review is approved and it is time to hand off to a human reviewer:

1. Convert the PR from draft to Ready for Review:
   ```
   mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, draft=false)
   ```
2. Look up the human reviewer's GitHub account via the `lookupJiraAccountId` operation from `work-with-Jira-tasks` with `$REVIEW_ASSIGNEE_EMAIL`.
3. Request their review:
   ```
   mcp__plugin_github_github__update_pull_request(owner=<owner>, repo=<repo>, pullNumber=<number>, reviewers=["<github-username>"])
   ```
