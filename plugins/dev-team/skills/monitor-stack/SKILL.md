---
name: monitor-stack
user-invocable: false
description: >
  Long-lived, one-per-epic PR monitor for a GitHub stack. Owns the entire post-hand-off
  lifecycle for every task in an epic's target set: repeatedly polls the whole stack via
  `stack_pr_poll.py`, reacting to exactly the one outcome each call returns — spawning `fix-pr`
  for a review comment or CI failure, resolving a rebase conflict via the developer agent, or
  halting once every task in the target set has merged. Replaces the per-task `monitor-pr` fleet.
argument-hint: --work-item-id <epic-id>
---

Use this skill when:
- The first task in an epic's target set has reached hand-off (its PR is open, registered into
  the epic's `gh stack`) and something needs to keep every task's PR in that stack in sync until
  it merges
- You were spawned to do exactly this — auto-started by `concurrent-orchestrate` the moment the
  first task in an epic's target set hands off, or manually via `/watch-stack <epic-key>`

Do NOT use this skill when:
- No task in the epic's target set has reached hand-off yet — there is no stack entry to monitor
- Every task in the target set has already merged and a prior run of this skill already halted
  for this epic

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `stack_pr_poll.py` lives in the sibling `workflow-orchestrate` skill's
`scripts/` directory, so it is invoked as
`<skill-dir>/../workflow-orchestrate/scripts/stack_pr_poll.py` — still anchored to `<skill-dir>`,
never to an assumed repo-root CWD.

## Role

You are the long-lived monitor for one epic's whole stack of PRs. You run as a single session
that stays alive for the epic's entire post-hand-off lifecycle — not a `/loop`-style recurring
re-invocation and not a scheduled/cron-triggered agent. You block inside `stack_pr_poll.py`,
react to whatever single outcome it returns, and repeat, until `stack_pr_poll.py` reports
`"epic_complete"` or an unresolved rebase conflict stops you.

**Never attempt to:**
- Call `gh stack` yourself, directly or indirectly — `work-with-stacked-prs` (via
  `stack_pr_poll.py`, which imports `gh_stack.py`) is the sole owner of every `gh stack`
  invocation in this feature. Every operation this skill needs comes indirectly through
  `stack_pr_poll.py`'s own return value.
- Resolve a rebase conflict yourself — spawn the developer agent to run `resolve-rebase-conflict`
- Fix a review comment or CI failure yourself — spawn `fix-pr` (nested, via the developer agent)
- Ask the user a question — `AskUserQuestion` is unavailable to any `Agent`-spawned sub-agent
  (confirmed experimentally); stop instead and let the harness's background-task notification
  surface the situation
- Reuse the implement-phase worktree of whichever task happened to trigger your auto-start — you
  run in your own, freshly spawned worktree, checked out on the epic's feature branch, not any
  one task's branch
- Reason about which task's branch the worktree should be on, or batch more than one fired event
  in a single pass — `stack_pr_poll.py` already resolved that ambiguity before returning; this
  skill only reacts to exactly the one thing it returned
- Count against `concurrent_schedule.py`'s `concurrency.max-parallel-tasks` cap — that cap only
  counts active task-pipeline spawns, never this monitor

## Steps

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else — even before step 2:

```bash
git status --short
```

Must be empty. If it produces any output, this is a **hard stop**: stop immediately and report
the failure in detail (do not proceed to step 2 or attempt any recovery). This guards against a
confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873, #41010) that
can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a dirty
worktree at this point means it isn't the fresh one this task expects.

### 2 — Resolve the epic's context file and check out the feature branch

Use the `use-context-file` skill with `<epic-id>` (this skill's own `--work-item-id` argument)
to locate and read (creating if necessary) the epic's own context file — per the spec's own
Interfaces note, this monitor's bookkeeping lives on the epic/feature-work-item's tracked
record, not any single task's context file, since one session now spans every task in the
stack. Note `watch_worktree_path`/`watch_worktree_branch` if already recorded by a prior run of
this skill for this epic.

Determine the epic's own feature branch — the trunk `gh stack` is anchored to — the same way
`ensure-feature-branch` step 2 does: read `git-repo.working-branches.feature` from the context
file's `Project Configuration` section, take its literal prefix up to the first `<placeholder>`
(`feature/`), then:

```bash
git fetch origin
git branch -r --sort=-committerdate | grep -E "<feature-prefix><epic-id>(-|$)"
```

Take the first line, strip the `origin/` prefix — that is `<feature-branch>`. By the time this
skill runs, a task in this epic has already reached hand-off, so `ensure-feature-branch` has
already created it; a missing match here is a **hard stop** — report the failure in detail rather
than guessing a branch name.

```bash
git checkout <feature-branch>
git pull origin <feature-branch>
```

From this point on, plain git commands work directly (no `git -C`) — the whole session's cwd is
already this worktree.

### 3 — Record this session's own worktree

Record this session's own worktree as `watch_worktree_path`/`watch_worktree_branch` on the
epic's context file via `use-context-file`, if not already recorded by an earlier pass of this
same run:

```bash
git rev-parse --show-toplevel   # -> watch_worktree_path
git rev-parse --abbrev-ref HEAD # -> watch_worktree_branch
```

Unlike `monitor-pr`, there is no single task's implement-phase worktree to remove here — this
skill's own worktree was never used for any one task's implementation, only for monitoring the
whole stack, so there is nothing to clean up before recording.

### 4 — Poll loop

Repeat the following indefinitely, until step 4b's `"epic_complete"` case stops you, or step 5's
`"unresolved"` case stops you.

#### 4a — Poll

```bash
python3 "<skill-dir>/../workflow-orchestrate/scripts/stack_pr_poll.py" <epic-id>
```

Parse stdout as JSON. It is exactly one of: `"conflict"`, `"epic_complete"`,
`{"task_work_item_id": ..., "event": "review_comment" | "ci_failure"}`, or `"no_change"` — never
a batch, and never any of `monitor-pr`'s retired `dependency_merged`/`base_updated`/rebase-
mechanic outcomes.

If `"no_change"`, go straight back to step 4a — `stack_pr_poll.py` already blocked internally for
its own bounded window; no additional wait is needed here.

If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
stop and report that error in detail.

#### 4b — React to exactly the one outcome returned

- **`"epic_complete"`** — every task in the target set has merged. Remove this session's own
  worktree/branch, then stop:
  ```bash
  cd "$(git rev-parse --path-format=absolute --git-common-dir)/.."
  git worktree remove <watch_worktree_path> --force
  git branch -D <watch_worktree_branch>
  ```
  (`cd` out first — a worktree cannot reliably remove itself while it's still the process's own
  cwd.) If either command exits non-zero, this is a **hard stop**: stop immediately and report
  the failure in detail instead of reporting success — a failed cleanup here must never be
  reported as a clean halt. Only once both commands succeed, report success: every task in the
  epic's target set has merged and the monitor has stopped.
- **`{"task_work_item_id", "event"}`** — a review comment or CI failure fired for that task.
  `stack_pr_poll.py` has already checked out that task's own branch itself — no checkout of your
  own is needed. Use the `use-context-file` skill to compute that task's own context file path
  (`<task_context_file>`), then spawn `fix-pr` against it (nested, via the developer agent):
  ```
  Agent(
    subagent_type: "dev-team:developer",
    prompt: "Invoke the `workflow-worker` skill with arguments:
  --context-file <task_context_file>
  --write-section Post-Handoff Fix <n>
  --skill fix-pr
  --skill-args <task_work_item_id>"
  )
  ```
  `Post-Handoff Fix <n>` is a section name on that task's own context file, distinct from the
  pre-hand-off pipeline's own `Fix N` numbering — start `<n>` at 1 for this run and increment it
  for each such spawn, regardless of which task it's for (one counter for the whole epic-wide
  session, not one per task). If the spawn reports anything other than `successful`, stop and
  report the failure in detail — do not retry automatically. Otherwise, return to step 4a.
- **`"conflict"`** — go to step 5.
- **`"no_change"`** — return to step 4a immediately.

### 5 — Resolve a rebase conflict

`stack_pr_poll.py` leaves the currently-conflicting task's branch mid-rebase (same
`.git/rebase-merge`/`.git/rebase-apply` state `rebase_onto()` used to leave, just now reached via
`gh stack sync`'s own cascade). Determine which task that is — `stack_pr_poll.py`'s `"conflict"`
result names no task, since the conflict can belong to any entry in the stack:

```bash
git_dir="$(git rev-parse --git-dir)"
head_name_file="$git_dir/rebase-merge/head-name"
[ -f "$head_name_file" ] || head_name_file="$git_dir/rebase-apply/head-name"
cat "$head_name_file"   # e.g. refs/heads/dev/claude/ADR-380
```

Strip the `refs/heads/` prefix and take the branch name's last `/`-separated segment (mirroring
the Stack PR event detector's own `name.rsplit("/", 1)[-1]` convention) — that is
`<conflicting_task_id>`.

Use the `read-task-brief` skill with `<conflicting_task_id>` to fetch that task's own brief/spec
context — the same content `resolve-rebase-conflict` needs as its argument to resolve conflict
regions unambiguously. Use the `use-context-file` skill to compute that task's own context file
path (`<task_context_file>`).

Spawn the developer agent, nested, with no `isolation` of its own — it inherits this session's
own worktree cwd, where the rebase is already left in progress:

```
Agent(
  subagent_type: "dev-team:developer",
  prompt: "Invoke the `workflow-worker` skill with arguments:
--context-file <task_context_file>
--write-section Rebase Conflict <n>
--skill resolve-rebase-conflict
--skill-args <task's brief/spec context text>"
)
```

(`<n>` increments the same way `Post-Handoff Fix <n>` does — once per conflict resolved during
this run, across the whole epic, not per task.) If the spawn itself reports anything other than
`successful`, stop and report the failure in detail.

Otherwise, read the content the spawned agent wrote to `Rebase Conflict <n>` in
`<task_context_file>` — this is `resolve-rebase-conflict`'s own `"resolved"` or `"unresolved"`
verdict, distinct from the spawn's generic `successful` status:

- **`"resolved"`** — do not push or run any further git command yourself. Return directly to
  step 4a: the very next `stack_pr_poll.py` call runs the `sync` operation as its own first
  action, which pushes and keeps `gh stack`'s own PR-position bookkeeping consistent — a raw
  `git push --force-with-lease` here would update the git ref but leave that bookkeeping stale.
- **`"unresolved"`** — run `git rebase --abort` to leave a clean worktree (no rebase in
  progress), then **stop this agent** — this halts monitoring for the whole epic, deliberately:
  `gh stack sync`'s cascading rebase already means one stuck task blocks every later task in the
  stack regardless of how many monitor processes exist, so concentrating the halt into this one
  process is the intended behavior, not an accepted side effect. There is no `AskUserQuestion`
  fallback. Your final message must describe the conflict in detail (which task, which files,
  which commit, why it couldn't be resolved with confidence) so it surfaces via the harness's
  background-task notification. A human resumes this same agent via `SendMessage`, or restarts
  fresh via `/watch-stack <epic-id>`.

## Skills

- `use-context-file` — reading/creating the epic's own context file, recording
  `watch_worktree_path`/`watch_worktree_branch`, and computing a task's own context file path for
  `fix-pr`/`resolve-rebase-conflict` spawns
- `read-task-brief` — sourcing the brief/spec context `resolve-rebase-conflict` needs as its
  argument for the currently-conflicting task
- `workflow-worker` — the mediated spawn pattern (`--context-file`/`--write-section`/`--skill`/
  `--skill-args`) for nested `fix-pr` and `resolve-rebase-conflict` calls
