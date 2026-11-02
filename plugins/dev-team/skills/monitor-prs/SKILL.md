---
name: monitor-prs
user-invocable: false
description: Only use when instructed.
---

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `stack_pr_poll.py`, `stack_rebase_continue.py`, `stack_checkout.py`, and
`pr_list_poll.py` all live in the sibling `workflow-orchestrate` skill's `scripts/` directory, so
they are invoked as `<skill-dir>/../workflow-orchestrate/scripts/stack_pr_poll.py`,
`<skill-dir>/../workflow-orchestrate/scripts/stack_rebase_continue.py`,
`<skill-dir>/../workflow-orchestrate/scripts/stack_checkout.py`, and
`<skill-dir>/../workflow-orchestrate/scripts/pr_list_poll.py` — still anchored to `<skill-dir>`,
never to an assumed repo-root CWD.

## Determining which mode to run

- **`--pr-numbers <pr1>[,<pr2>...]` given** — **PR mode**. Read `references/pr-mode.md` and
  follow it — none of stack mode's steps apply.
- **Otherwise** (`--work-item-id <epic-id>` given, or no argument at all) — **stack mode**. Read
  `references/stack-mode.md` and follow it.

The two are mutually exclusive — `--pr-numbers` is never combined with `--work-item-id`; a
stack's PRs are always discovered via the epic id or the current worktree, never listed by hand.
Only one of the two reference files is ever relevant to a given invocation — read the one your
mode selected, not both.

## Role

You are a long-lived PR monitor — either for one epic's whole stack (stack mode) or for a fixed,
explicit list of PRs (PR mode). Either way you run as a single session that stays alive for the
monitored PR(s)' entire post-hand-off lifecycle — not a `/loop`-style recurring re-invocation and
not a scheduled/cron-triggered agent. You block inside a poll script, react to whatever single
outcome it returns, and repeat, until every monitored PR merges or (stack mode only) an
unresolved rebase conflict stops you.

**Never attempt to:**
- Call `gh stack` yourself, directly or indirectly, **in stack mode** — `work-with-stacked-prs`
  (via `stack_pr_poll.py`, `stack_rebase_continue.py`, and `stack_checkout.py`, which all import
  `gh_stack.py`) is the sole owner of every `gh stack` invocation in this feature. Every operation
  this skill needs comes indirectly through one of those three scripts' own return values. **In
  PR mode, `gh stack` is never relevant in the first place** — `pr_list_poll.py` never touches it.
- Resolve a rebase conflict yourself — spawn the developer agent to run `resolve-rebase-conflict`
  (stack mode only; PR mode has no rebase-cascade concept, so this never arises there)
- Fix a review comment or CI failure yourself — spawn `fix-pr` (nested, via the developer agent)
- Auto-fix a human-authored PR comment — a human comment deserves a personal response, not a bot
  edit; notify the user instead (stack mode's step 4b / PR mode's step 1b) and never spawn
  `fix-pr` for it
- Ask the user a question — `AskUserQuestion` is unavailable to any `Agent`-spawned sub-agent
  (confirmed experimentally), which this skill may or may not currently be (stack mode's step 2a
  covers both an isolated auto-started spawn and a direct in-session invocation; PR mode is
  always a direct in-session invocation); treat it as unavailable either way for consistency.
  Stop instead and let the harness's background-task notification surface the situation
- Reuse the implement-phase worktree of whichever task happened to trigger your auto-start when
  running your own dedicated worktree (stack mode's step 2a) — checked out on a real stack member
  branch, never the epic's trunk itself and never any one task's own implement-phase worktree
- Reason about which task's branch the worktree should be on, or batch more than one fired event
  in a single pass — the poll script already resolved that ambiguity before returning; this
  skill only reacts to exactly the one thing it returned
- Count against `concurrent_schedule.py`'s `concurrency.max-parallel-tasks` cap — that cap only
  counts active task-pipeline spawns, never this monitor

## Skills

- `use-context-file` — stack mode: reading/creating the epic's own context file, recording
  `watch_worktree_path`/`watch_worktree_branch`, and (both modes) computing a task's own context
  file path for `fix-pr`/`resolve-rebase-conflict` spawns
- `read-task-brief` — sourcing the brief/spec context `resolve-rebase-conflict` needs as its
  argument for the currently-conflicting task (stack mode only)
- `workflow-worker` — the mediated spawn pattern (`--context-file`/`--write-section`/`--skill`/
  `--skill-args`) for nested `fix-pr` (both modes) and `resolve-rebase-conflict` (stack mode only)
  calls
- `workflow-troubleshoot` (via the `dev-team:troubleshooter` agent) — diagnosing and logging an
  unexpected failure at one of the points named in your mode's own reference file, under
  "Running the troubleshooter agent"
