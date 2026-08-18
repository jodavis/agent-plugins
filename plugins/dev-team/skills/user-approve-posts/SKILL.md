---
name: user-approve-posts
user-invocable: false
description: >
  Use when a batch of proposed posts (Jira/GitHub comments, a Jira description update, or a PR
  status comment) needs the user's approval before it is actually sent. Owns the whole batch end
  to end — present, edit, discuss, attribute, dispatch, and clean up — for as few as one entry or
  as many as the queue holds.
argument-hint: posts <json-array>
---

Use this skill when:
- `/dev-team:review-posts` has built a list of proposed posts from the pending-posts queue and
  needs them approved
- Any synchronous/interactive flow has one or more proposed posts (even a list of one) that
  should be reviewed by the user before posting

Do NOT use this skill when:
- Nothing is running in an interactive session with `AskUserQuestion` available — this skill is
  only ever invoked from the user's own interactive session (e.g. via `/dev-team:review-posts`),
  never from an unattended pipeline agent

## Arguments

- `posts` — a JSON array of `PostEntry` objects:
  `{content: str, channel: "jira-comment" | "jira-description" | "github-issue-comment" |
  "pr-comment", target: str, file_path: str | null}`. `target` is a Jira issue key, GitHub issue
  key, or PR URL, matching `channel`. `file_path`, when set, is the file this entry's content
  came from (typically the caller's own queue file) — "Edit and approve" re-reads it. Passed as
  a JSON-array argument, the same convention `run-hook-instructions` uses for its own
  `--instructions <json-array>` argument.

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. This skill may run in a repo other than the one containing these plugin
files (e.g. as an installed plugin), so always resolve paths this way rather than assuming a
particular repo layout or that the `Bash` tool's CWD is the repo root.

## What this skill owns

Every step of getting one batch of proposed posts approved: presenting each entry to the user,
editing, deferring "Discuss this" entries to a one-at-a-time second pass, resolving the
reviewed-by attribution line once for the whole call, dispatching each approved entry to the
channel that actually posts it, and deleting each entry's file the moment it resolves — posted
or rejected. Nothing is threaded back through a per-entry return value; the only output is the
final `posted`/`rejected` counts once every entry, immediate or deferred, is resolved.

A list of one behaves identically to any other list — there is no queue/file dependency beyond
the optional `file_path` on that one entry.

## Steps

### 1 — Resolve `<user-name>` once for the whole call

Try each of the following in order, stopping at the first that succeeds:

1. `work-with-Jira-tasks`'s `atlassianUserInfo` operation, if a Jira/Atlassian MCP server is
   connected. Use the returned display name.
2. `gh api user --jq .login`, for a GitHub-only project (no Jira/Atlassian MCP server
   connected). Use the returned login.
3. `git-repo.user-alias` from Project Configuration (via `get-project-configuration`, or the
   already-resolved context file's `Project Configuration` section if one is available).

Use this one resolved `<user-name>` for every entry dispatched during this call — do not
re-resolve it per entry.

### 2 — First pass: batch through `AskUserQuestion`

Walk `posts` in batches of up to 4 at a time. For each entry in a batch, ask via
`AskUserQuestion` with four options: "Approve as-is," "Edit and approve," "Discuss this,"
"Reject." Show the entry's `content`, `channel`, and `target` so the user can identify it.

For each answer in the batch, resolve it immediately except "Discuss this" (see below):

- **"Approve as-is"** — dispatch the entry's current `content` as-is (see step 4).
- **"Edit and approve"**:
  - If `file_path` is set, re-read that file's current content now (the user may already have
    edited it directly, before or during review).
  - If `file_path` is unset, create a fresh temp file under
    `~/.dev-team/<repo-slug>/user-approve-posts-tmp/` (never inside `pending-posts/`, so it's
    never mistaken for a pending queue entry — see "Computing `<repo-slug>`" below) containing
    the entry's current `content`. Report the path to the user and wait for them to confirm
    they're done editing before re-reading it.
  - Either way, dispatch the re-read content (see step 4).
- **"Reject"** — discard the entry; do not dispatch it. Still delete its file (step 4's cleanup
  applies to rejections too).
- **"Discuss this"** — set the entry aside for the second pass (step 3). Leave its file, if any,
  untouched. Do not resolve it now.

### 3 — Second pass: one-at-a-time discussion

Once every non-deferred entry from step 2 is resolved, revisit each "Discuss this" entry in
order, one at a time, as an open-ended conversation — not another batched `AskUserQuestion`
call. This follows the same precedent `document-discussion` already establishes for its own
`> **Review:**` comment loop: present the entry, answer the user's questions and incorporate
their feedback, and keep the conversation open until they reach a clear approve or reject
decision (with edits applied the same way as step 2's "Edit and approve," if requested). Once
resolved, dispatch or discard it exactly as step 2 would (step 4).

### 4 — Dispatching and cleanup (applies to every entry, either pass)

The moment an entry is approved (as-is or edited), append
`"Written by Claude Code and reviewed by <user-name> before posting."` to its content as its own
trailing line (blank line before it, matching `message-attribution`'s own formatting rule), then
dispatch by `channel`:

| `channel` | Dispatch to |
|---|---|
| `jira-comment` | `work-with-Jira-tasks`'s `addCommentToJiraIssue` operation, `target` as the issue key |
| `jira-description` | `work-with-Jira-tasks`'s `editJiraIssue` operation, setting `description` on `target` |
| `github-issue-comment` | `work-with-GitHub-issues`'s "Add a comment" operation, `target` as the issue key |
| `pr-comment` | `work-with-pr`'s `post-comment` operation, `target` as the PR URL |

Each of these dispatch operations already calls `message-attribution` internally before
posting (per their own SKILL.md files) and appends any configured `attribution.message` line on
top of whatever content is passed in — do not call `message-attribution` again here and do not
duplicate that line; the reviewed-by line above is additive to it, not a replacement, exactly as
`message-attribution` requires for any existing trailer.

Whether the entry was approved and dispatched, or rejected and discarded, delete whatever file
it was using — its caller-supplied `file_path`, or a temp file this skill created in step 2 —
the moment the entry resolves. Do not batch deletions until the end.

### 5 — Return the final counts

Once every entry — immediate (step 2) or deferred (step 3) — is resolved, return
`{"posted": <count of dispatched entries>, "rejected": <count of discarded entries>}`.

## Computing `<repo-slug>`

`user-approve-posts` is agent-skill prose, not a Python script, so it has no `__file__` of its
own to derive a relative import path from the way `queue_post.py` does. Reach the same
`get_repo_slug()` function `queue_post.py` and `concurrent_schedule.py` already use, via a
`python3 -c` one-liner through `Bash`, resolving the path relative to `<skill-dir>` the same way
`dev-spec-create-work-items` reaches `task_dependencies.py`:

```bash
python3 -c "
import sys
sys.path.insert(0, '<skill-dir>/../workflow-orchestrate/scripts')
from get_context_path import get_repo_slug
print(get_repo_slug())
"
```

This respects `GIT_REMOTE_URL_OVERRIDE` (a test seam) automatically, since `get_repo_slug()`
itself checks that env var before falling back to `git remote get-url origin`.

To compute the full `user-approve-posts-tmp` directory (respecting `DEV_TEAM_STATE_DIR`, the
same test seam `queue_post.py`'s own `_state_dir()` honors, so tests never write into a real
machine's `~/.dev-team/`):

```bash
python3 -c "
import os, sys
from pathlib import Path
sys.path.insert(0, '<skill-dir>/../workflow-orchestrate/scripts')
from get_context_path import get_repo_slug
base = Path(os.environ['DEV_TEAM_STATE_DIR']) if os.environ.get('DEV_TEAM_STATE_DIR') else Path.home() / '.dev-team'
print(base / get_repo_slug() / 'user-approve-posts-tmp')
"
```

Create the directory (`mkdir -p`) before writing a temp file into it the first time it's needed
during a call; it does not need to exist up front.
