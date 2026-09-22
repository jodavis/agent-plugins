---
name: resolve-pr-reference
user-invocable: false
description: >
  Use when you need to resolve a PR reference — a bare number/`#123`, a full GitHub PR URL,
  or a work-item ID — to exactly one owner/repo#number. Delegates every deterministic path to
  resolve_pr_reference.py; makes one inline getJiraIssueRemoteIssueLinks MCP call itself for
  the Jira work-item path.
argument-hint: <ref>
---

Use this skill when:
- You have a PR reference (a bare number, `#123`, a full GitHub PR URL, or a work-item ID)
  and need it resolved to exactly one `owner/repo#number`, or a structured failure

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

## Resolution paths

Every path except the Jira work-item path is fully deterministic and handled by
`resolve_pr_reference.py`:

- A full GitHub PR URL (`https://github.com/<owner>/<repo>/pull/<number>`) resolves to that
  URL's own owner/repo/number, independent of the current repo.
- A bare PR number, or `#123`, resolves against the current repo's `origin`.
- A ref matching a configured provider's `work-tracking.<provider>.issue-key-pattern`/
  `recognize-patterns` (via `get-project-configuration`) is treated as a work-item ID:
  - First, an existing `use-context-file` context file for that work-item ID is checked; if
    found and its `pr_url` field is set, that's used directly — no provider is queried.
  - Otherwise, dispatch by provider:
    - **GitHub**: `resolve_pr_reference.py` calls the new `getLinkedPullRequests` operation
      (documented in `work-with-GitHub-issues`) directly — a plain `gh api graphql` call, no
      MCP tool needed.
    - **Jira**: the first script call (no `--jira-links` flag) reports `status: "needs_jira_links"`
      instead of resolving — see below, this is the one path this skill itself performs a
      tool-use call for.
- A ref matching none of the above shapes is `not_found`, with `detail` distinguishing it from a
  well-formed reference that resolved to nothing.

## Steps

### 1 — Run the script without Jira links

```bash
python3 "<skill-dir>/scripts/resolve_pr_reference.py" "<ref>"
```

If the result's `status` is `resolved`, `not_found`, `ambiguous`, or `access_denied`, that result
is final — skip step 2.

If the result's `status` is `needs_jira_links`, the ref matched the `jira` provider's configured
patterns and no `use-context-file` context file already resolved it — proceed to step 2.

The script also exits non-zero with `Error: ...` on stderr for a hard failure unrelated to ref
resolution itself (not part of the documented JSON contract) — stop and report that verbatim
rather than treating it as a resolution result.

### 2 — Jira work-item path only

Run this step only when step 1 returned `status: "needs_jira_links"`.

Call the `getJiraIssueRemoteIssueLinks` operation (documented in `work-with-Jira-tasks`'s
Operations table) with the work-item's issue key, to fetch its Remote Issue Links. Then re-run
the script, passing the result as JSON:

```bash
python3 "<skill-dir>/scripts/resolve_pr_reference.py" "<ref>" --jira-links '<json array of links, possibly empty>'
```

If `getJiraIssueRemoteIssueLinks` returns nothing, pass an empty array (`[]`) — the script's own
GitHub-search fallback (`gh pr list`/`gh search prs` for the issue key in title, body, or branch
name) runs before reporting `not_found`. This second call's result (`resolved`, `not_found`, or
`ambiguous`) is always final.

## Output contract

On success, one JSON object on stdout:

```json
{"status": "resolved", "owner": "...", "repo": "...", "number": 123,
 "pr_url": "https://github.com/.../pull/123",
 "source": "url" | "number" | "work-item-context-file" | "work-item-jira-remote-link"
   | "work-item-jira-github-search" | "work-item-github-linked-pr"}
```

On a pending Jira lookup (only possible from step 1, before step 2 has run):

```json
{"status": "needs_jira_links", "detail": "<why the Jira lookup is required>"}
```

On failure:

```json
{"status": "not_found" | "ambiguous" | "access_denied", "detail": "<what exactly failed>"}
```

- `not_found` — the ref didn't match any recognized shape, a matched provider pattern resolved
  to zero PRs (even after any fallback), or a resolved PR doesn't exist.
- `ambiguous` — more than one PR was found for a work-item ID; never guessed.
- `access_denied` — a resolved PR exists but isn't accessible (e.g. a private repo without
  permission).

Callers (worktree creation, evidence gathering, and other later PR-review-guide deliverables)
consume this JSON directly rather than re-deriving any of the above resolution logic themselves.
