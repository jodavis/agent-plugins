---
name: create-review-worktree
user-invocable: false
description: >
  Stands up an isolated working copy checked out to a resolved PR's head — an `EnterWorktree`
  worktree for a same-repo PR, a `git worktree add` from a sibling clone or a scratch `gh repo
  clone` for a cross-repo PR — so later Code Review Helper steps can operate on the PR's code
  without touching the reviewer's own checkout.
argument-hint: <resolved-pr-json>
---

Use this skill when:
- `review-pr` has a `resolve-pr-reference` result with `status: resolved` and needs an isolated
  working copy checked out to that PR's actual head commit

Do NOT use this skill when:
- `resolve-pr-reference` reported `not_found`/`ambiguous`/`access_denied` — `review-pr` reports
  that failure verbatim and stops; no worktree is created
- You need to clean up a worktree/clone this skill created — that is `review-pr`'s own job
  (`decide_cleanup_action.py`), out of scope here

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable.

Do not confuse the native `EnterWorktree`/`ExitWorktree` tools this skill uses with the
*different* `isolation: "worktree"` parameter the `Agent` tool takes elsewhere in this plugin
(e.g. `concurrent-orchestrate`) — that parameter isolates a freshly spawned **subagent** into its
own worktree; `EnterWorktree` instead puts the *current* session's own working directory into a
fresh worktree.

## Input

This skill's argument is `resolve-pr-reference`'s JSON output for a `status: resolved` PR:

```json
{"status": "resolved", "owner": "...", "repo": "...", "number": 123,
 "pr_url": "https://github.com/.../pull/123", "source": "..."}
```

## Return contract

Regardless of which mechanism was used, report back exactly one JSON object:

```json
{"isolation_kind": "enterworktree" | "sibling-worktree" | "scratch-clone",
 "worktree_path": "<absolute path to the working copy>",
 "head_ref": "<local branch name the working copy is now on>"}
```

This is the value `review-pr` passes to `review-session-context` to persist into
`.dev-team-review.md`'s `isolation_kind` and `worktree_path` fields — per the "one writer" rule,
this skill never writes that file itself.

## Steps

### 1 — Classify which isolation mechanism applies

```bash
python3 "<skill-dir>/scripts/create_review_worktree.py" classify '<resolved-pr-json>'
```

Prints one JSON object:

```json
{"repo_scope": "same-repo", "isolation_kind": "enterworktree"}
```
or
```json
{"repo_scope": "cross-repo", "isolation_kind": "sibling-worktree", "sibling_path": "..."}
```
or
```json
{"repo_scope": "cross-repo", "isolation_kind": "scratch-clone"}
```

If the command exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
stop and report that error in detail.

### 2 — Same-repo: enter a fresh worktree and check out the PR's head

Only when step 1 returned `isolation_kind: enterworktree`. This is the one mechanism the script
cannot perform itself: `EnterWorktree` is a native tool, callable only from this agent's own
tool-use turn — no script in this repo calls it, and none can.

1. Call the `EnterWorktree` tool (no arguments — it auto-assigns the worktree's directory under
   `.claude/worktrees/` and switches this session's own working directory into it). Do not try to
   force a name or path onto this call.
2. Run, in the now-current working directory:
   ```bash
   gh pr checkout <number> -R <owner>/<repo>
   ```
   This moves the fresh worktree off its default branch-from-main and onto the PR's actual head.
   If this fails, stop and report the failure in detail — no cleanup is attempted here (per
   `resolve-pr-reference`'s failure contract elsewhere, error handling for `gh`/`git` failures in
   this skill is to propagate them, not invent a structured retry).
3. Determine the working copy's path and the branch `gh pr checkout` landed on:
   ```bash
   pwd
   git rev-parse --abbrev-ref HEAD
   ```
4. Report:
   ```json
   {"isolation_kind": "enterworktree", "worktree_path": "<pwd output>", "head_ref": "<branch name>"}
   ```

Skip step 3 entirely — it only applies to the cross-repo paths.

### 3 — Cross-repo: stand up the sibling worktree or scratch clone

Only when step 1 returned `isolation_kind: sibling-worktree` or `scratch-clone`. Both mechanisms
are fully scriptable — no native tool call is needed for either.

```bash
python3 "<skill-dir>/scripts/create_review_worktree.py" finish-cross-repo '<resolved-pr-json>'
```

This performs, depending on which mechanism step 1 selected:
- **`sibling-worktree`:** `git worktree add` from the matching `../<repo>` sibling clone into
  `.claude/worktrees/review-<owner>-<repo>-<number>/`, then `gh pr checkout` inside it.
- **`scratch-clone`:** `gh repo clone <owner>/<repo>` into
  `.claude/worktrees/review-<owner>-<repo>-<number>/`, then `gh pr checkout` inside it.

Prints the same return-contract JSON shape documented above on success. If the command exits
non-zero, it prints a clear `Error: ...` message to stderr (covering `git worktree add`,
`gh repo clone`, or `gh pr checkout` failing — e.g. auth, network, or a dirty/colliding
destination) — stop and report that error in detail; this skill does not invent a structured
failure taxonomy for these failures the way `resolve-pr-reference` does for PR resolution.

---

Report the final JSON object from step 2 or step 3 back to the caller (`review-pr`). Do not write
`.dev-team-review.md` yourself — that belongs to `review-session-context`.
