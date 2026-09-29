---
name: gather-pr-evidence
user-invocable: false
description: >
  Use when a caller (e.g. `review-pr`) needs a structured evidence bundle for one resolved PR —
  diff, description, existing inline review comments, and related work items — gathered from a
  worktree/clone already checked out to that PR. Always spawned via the `Agent` tool with
  `subagent_type: "general-purpose"` (never `fork`), so its intermediate tool-call noise never
  reaches the caller's own context; its only return value is the evidence bundle.
argument-hint: <worktree-or-clone-absolute-path> <owner>/<repo>#<number>
---

Use this skill when:
- You are the subagent spawned to gather one PR's review evidence, given this skill's own
  instructions as your prompt
- You have been given a worktree/clone's absolute path (already checked out to the target PR,
  by `create-review-worktree`) and the resolved PR identity (`owner/repo#number`, per
  `resolve-pr-reference`'s output contract)

Do NOT use this skill when:
- You are the caller deciding whether/how to spawn this subagent — that is the caller's own
  concern (e.g. `review-pr`), not something this file's instructions cover
- You need to persist the evidence bundle anywhere — this skill only returns it as its final
  message; persisting it (e.g. to `.dev-team-review.md`) is the caller's job

This skill is self-contained: everything you need to gather the evidence is in this file. You
have no memory of the conversation that spawned you and no access to it beyond the two
arguments above.

## Inputs

- `<worktree-or-clone-absolute-path>` — run every shell command and file read in this task under
  this path. **Never operate against any other repo checkout** (including one that happens to be
  the current working directory) — this explicit path is always the target.
- `<owner>/<repo>#<number>` — the resolved PR identity. The diff, description, and comments (steps
  1-3) are fetched from GitHub directly via this identity, independent of the worktree/clone path;
  the worktree/clone path only matters for step 4's project-configuration read.

## Steps

### 1 — Fetch the diff

Use `work-with-pr`'s documented call:
```
pull_request_read(method="get_diff", owner=<owner>, repo=<repo>, pullNumber=<number>)
```

### 2 — Fetch the PR description

`work-with-pr`'s `SKILL.md` does not document an operation for the PR's own description/body.
Use:
```bash
gh pr view <number> --repo <owner>/<repo> --json body --jq .body
```
run under `<worktree-or-clone-absolute-path>`. An empty body is a valid result — use `""`, not an
error.

### 3 — Fetch existing inline review comments

Use `work-with-pr`'s documented call:
```
pull_request_read(method="get_review_comments", owner=<owner>, repo=<repo>, pullNumber=<number>)
```
For each thread returned, shape its first comment (`comments.nodes[0]`) into
`{"path", "line", "body", "author"}`:
- `path` and `body` come directly from `comments.nodes[0]`.
- `line` and `author` are not shown in `work-with-pr`'s own documented response shape — read them
  directly off the actual tool response for this call (e.g. `comments.nodes[0].line` and
  `comments.nodes[0].author.login`, or whichever equivalent fields the connected MCP server
  returns). If a field is genuinely absent from the live response, use `null` for it rather than
  omitting the key.

No threads → `comments: []`.

### 4 — Read the target repo's project configuration

Use `get-project-configuration`, resolved from `<worktree-or-clone-absolute-path>` — **never**
the calling session's own repo. If `work-tracking` comes back `null` or absent, there is nothing
to scan for: skip straight to step 6 with `related_work_items: []`.

### 5 — Scan for and resolve related work items

For each provider configured under `work-tracking` (only `jira` and `github` have adapters —
skip any other configured key), collect its `issue-key-pattern` and any `recognize-patterns`.
Search for a match against those patterns in:
- the PR description (step 2's result), and
- the PR's branch name: `gh pr view <number> --repo <owner>/<repo> --json headRefName --jq
  .headRefName`, also run under the worktree/clone path.

**Do not use `identify-project-work-items`** — its documented fallback (asking the user
interactively) is unreachable from this subagent's context, since there is no user turn to ask
into. Match the configured regex patterns directly instead.

For every distinct match found, resolve it via the matching provider's adapter:
- `jira` match → `work-with-Jira-tasks`'s `getJiraIssue` operation, keyed by the matched issue
  key; take the issue's summary field as `summary`.
- `github` match → `work-with-GitHub-issues`'s issue-read operation
  (`mcp__plugin_github_github__issue_read`, or `gh issue view <n>`), keyed by the matched issue
  number; take the issue's title as `summary`.

Populate each resolved match as `{"id": "<matched key/number>", "provider": "jira" | "github",
"summary": "<resolved summary/title>"}`. Deduplicate repeated matches of the same id (e.g. the
same reference appearing in both the description and the branch name).

No matches (or `work-tracking` not configured) → `related_work_items: []` — a present, empty
list, never an omitted key and never an error.

### 6 — Return the evidence bundle

Return exactly one JSON object as your final message, with no prose before or after it:

```json
{"diff": "<unified diff text>", "description": "<PR body>",
 "comments": [{"path": "...", "line": 12, "body": "...", "author": "..."}],
 "related_work_items": [{"id": "AIP-12", "provider": "jira", "summary": "..."}]}
```

All four top-level keys are always present, even when a list value is empty.
