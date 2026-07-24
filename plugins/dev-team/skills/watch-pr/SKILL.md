---
name: watch-pr
user-invocable: false
description: >
  Long-lived, user-started post-hand-off PR monitor. Owns the entire lifecycle from hand-off to
  merge for one task's PR: repeatedly polls for new review comments, CI failures, base-branch
  moves, and dependency merges, reacting to every fired event — rebasing, spawning `fix-pr` for
  review/CI issues, resolving rebase conflicts via the developer agent, and halting once the
  task's own PR merges.
argument-hint: --work-item-id <work-item-id>
---

Use this skill when:
- A task's `workflow-orchestrate` run has reached hand-off (its PR is open and awaiting human
  review) and something needs to keep that PR in sync until it merges
- You were spawned to do exactly this — auto-started by `concurrent-orchestrate` the moment its
  target task hands off, or manually via `/watch-pr <work-item-id>`

Do NOT use this skill when:
- The task has not reached hand-off yet — there is no PR to monitor
- The task's PR has already merged and a prior run of this skill already halted for it

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `watch_pr_poll.py`, `pr_event_detector.py`, and `rebase_mechanic.py` all
live in the sibling `workflow-orchestrate` skill's `scripts/`
directory, so they are invoked as `<skill-dir>/../workflow-orchestrate/scripts/<script>.py` —
still anchored to `<skill-dir>`, never to an assumed repo-root CWD.

## Role

You are the long-lived monitor for one task's PR. You run as a single session that stays alive
for the task's entire post-hand-off lifecycle — not a `/loop`-style recurring re-invocation and
not a scheduled/cron-triggered agent. You block inside `watch_pr_poll.py`, react to whatever it
returns, and repeat, until the task's own PR merges or an unresolved rebase conflict stops you.

**Never attempt to:**
- Resolve a rebase conflict yourself — spawn the developer agent to run `resolve-rebase-conflict`
- Fix a review comment or CI failure yourself — spawn `fix-pr` (nested, via the developer agent)
- Ask the user a question — `AskUserQuestion` is unavailable to any `Agent`-spawned sub-agent
  (confirmed experimentally); stop instead and let the harness's background-task notification
  surface the situation
- Reuse the implement-phase worktree — you run in your own, freshly spawned one; you remove the
  old one as one of your first actions
- Count against `concurrent_schedule.py`'s `concurrency.max-parallel-tasks` cap — that cap only
  counts active task-pipeline spawns, never this monitor

## Steps

### 1 — Worktree-freshness check

Run this first, unconditionally, before anything else — even before step 2:

```bash
git stash list
git status --short
```

Both must be empty. If either produces any output, this is a **hard stop**: stop immediately and
report the failure in detail (do not proceed to step 2 or attempt any recovery). This guards
against a confirmed upstream `isolation: "worktree"` bug (Claude Code issues #51596, #37873,
#41010) that can silently reuse a stale worktree/branch on an 8-hex-char ID-prefix collision — a
dirty worktree at this point means it isn't the fresh one this task expects.

### 2 — Resolve the context file and check out the working branch

Use the `use-context-file` skill with the `work-item-id` to locate and read the context file. Note
`working_branch`, `base_branch`, `worktree_path`, and `worktree_branch` (the implement-phase
worktree's own path/branch, recorded before hand-off).

```bash
git fetch origin
git checkout <working_branch>
```

From this point on, plain git commands work directly (no `git -C`) — the whole session's cwd is
already this worktree.

### 3 — Remove the implement-phase worktree and record this one

The implement-phase worktree (`worktree_path`/`worktree_branch`, created before hand-off) is no
longer needed — this session runs in its own, freshly spawned worktree.

If `worktree_path` and `worktree_branch` are both empty (no implement-phase worktree was
recorded — e.g. a plain single-task run whose spawn predates this bookkeeping), skip straight to
the recording step below.

Otherwise, remove it:

```bash
git worktree remove <worktree_path> --force
git branch -D <worktree_branch>
```

`--force` is deliberate here: the worktree should be clean post hand-off, but this removal must
not get blocked by any stray state left behind by earlier spawned sub-agents. If either command
exits non-zero, this is a **hard stop**: stop immediately and report the failure in detail — do
not proceed to the recording step below or attempt any further recovery.

Record this session's own worktree as `watch_worktree_path`/`watch_worktree_branch` via
`use-context-file`:

```bash
git rev-parse --show-toplevel   # -> watch_worktree_path
git rev-parse --abbrev-ref HEAD # -> watch_worktree_branch
```

Also clear `worktree_path` and `worktree_branch` to empty via `use-context-file` — once removed,
they no longer point to a valid worktree.

### 4 — Poll loop

Repeat the following indefinitely, until step 4b's `task_merged` case stops you, or step 5's
`"unresolved"` case stops you.

#### 4a — Poll

```bash
python "<skill-dir>/../workflow-orchestrate/scripts/watch_pr_poll.py" <work-item-id>
```

Parse stdout as JSON. If it is the literal string `"no_change"`, go straight back to step 4a —
`watch_pr_poll.py` already blocked internally for its own bounded window; no additional wait is
needed here.

If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
stop and report that error in detail.

#### 4b — React to every fired event, rebase-related first

The result is a list that may contain more than one fired event in the same pass — handle all of
them before returning to 4a, in this order:

0. **`task_merged`, if present, takes absolute precedence over everything else in this list** —
   the task's own PR has merged, so nothing else fired alongside it (a rebase, a review comment,
   a CI result) is still actionable against a PR that's already closed. Remove this session's own
   worktree/branch, then stop, skipping bullets 1–3 below entirely for this pass:
   ```bash
   cd "$(git rev-parse --path-format=absolute --git-common-dir)/.."
   git worktree remove <watch_worktree_path> --force
   git branch -D <watch_worktree_branch>
   ```
   (`cd` out first — a worktree cannot reliably remove itself while it's still the process's own
   cwd.) If either command exits non-zero, this is a **hard stop**: stop immediately and report
   the failure in detail instead of reporting success — a failed cleanup here must never be
   reported as a clean halt. Only once both commands succeed, report success: the task's PR has
   merged and its monitor has stopped.

Otherwise, handle every one of the remaining event types present in this pass, rebase-related
first, **before** returning to step 4a — do not re-poll partway through:

1. **`dependency_merged`** — re-read `base_branch` from the context file via `use-context-file`.
   `pr_event_detector.py` already re-targeted it (to wherever the dependency's PR actually merged
   — usually the feature branch, but possibly another still-open task's branch in an
   out-of-order case) and already persisted that write itself; do not write `base_branch` again
   here. Then run the rebase mechanic (step 4c) using this freshly-read value.
2. **`base_updated`** (and `dependency_merged` was not also present) — run the rebase mechanic
   (step 4c) using the `base_branch` already on file; it hasn't changed identity, only moved
   forward.

   Either way, once the rebase mechanic (step 4c) concludes with `"rebased"`, or step 5 concludes
   a conflict with `"resolved"` and this session's own push succeeds, continue on to bullet 3
   below **for this same pass** — the events it names already fired and were marked seen by
   `pr_event_detector.py` the moment `watch_pr_poll.py` returned them, so skipping them here
   would silently drop them, not just defer them to the next poll. (If step 5 instead concludes
   `"unresolved"`, this agent stops entirely per step 5 — bullet 3 is moot.)
3. **`review_comment`** and/or **`ci_failure`** — if either or both fired this pass, spawn `fix-pr`
   **once** (not once per event type — `fix-pr`'s own step 4 already fetches both open review
   comment threads and PR check failures together in one pass):
   ```
   Agent(
     subagent_type: "dev-team:developer",
     prompt: "Invoke the `workflow-worker` skill with arguments:
   --context-file <context_file>
   --write-section Post-Handoff Fix <n>
   --skill fix-pr
   --skill-args <work-item-id>"
   )
   ```
   `Post-Handoff Fix <n>` is a section name distinct from the pre-hand-off pipeline's own
   `Fix N` numbering (owned by `dev_team.py`'s state machine, which this loop never runs
   through) — start `<n>` at 1 and increment it for each such spawn made during this run. If the
   spawn reports anything other than `successful`, stop and report the failure in detail — do not
   retry automatically.

If none of the above fired but the list was non-empty (should not happen — `watch_pr_poll.py`
only returns a non-empty list when `detect_pr_events` reports a real fired event), treat it the
same as `"no_change"` and return to step 4a.

Once every event in this pass has been handled, return to step 4a.

#### 4c — Run the rebase mechanic

```bash
python -c "
import sys
sys.path.insert(0, '<skill-dir>/../workflow-orchestrate/scripts')
from pathlib import Path
from rebase_mechanic import rebase_onto
print(rebase_onto('<working_branch>', '<base_branch>', Path.cwd()))
"
```

- **`rebased`** — the mechanic already fetched, rebased, and force-pushed with lease. Continue
  with step 4b's bullet 3 for this same pass.
- **`conflict`** — go to step 5.

### 5 — Resolve a rebase conflict

Use the `read-task-brief` skill with the `work-item-id` to fetch this task's own brief/spec
context — the same content `resolve-rebase-conflict` needs as its argument to resolve conflict
regions unambiguously.

Spawn the developer agent, nested, with no `isolation` of its own — it inherits this session's
own worktree cwd, where the rebase is already left in progress:

```
Agent(
  subagent_type: "dev-team:developer",
  prompt: "Invoke the `workflow-worker` skill with arguments:
--context-file <context_file>
--write-section Rebase Conflict <n>
--skill resolve-rebase-conflict
--skill-args <task's brief/spec context text>"
)
```

(`<n>` increments the same way `Post-Handoff Fix <n>` does — once per conflict resolved during
this run.) If the spawn itself reports anything other than `successful`, stop and report the
failure in detail.

Otherwise, read the content the spawned agent wrote to `Rebase Conflict <n>` in the context file
— this is `resolve-rebase-conflict`'s own `"resolved"` or `"unresolved"` verdict, distinct from
the spawn's generic `successful` status:

- **`"resolved"`** — run `git push --force-with-lease origin <working_branch>` yourself (not
  routed back through `rebase_onto()`, which already exited on the conflict). Continue with step
  4b's bullet 3 for the same pass that triggered this conflict (not step 4a directly) — any
  `review_comment`/`ci_failure` already marked seen in that pass still needs handling.
- **`"unresolved"`** — run `git rebase --abort` to leave a clean worktree (no rebase in progress),
  then **stop this agent**. There is no `AskUserQuestion` fallback. Your final message must
  describe the conflict in detail (which files, which commit, why it couldn't be resolved with
  confidence) so it surfaces via the harness's background-task notification. A human resumes this
  same agent via `SendMessage`, or restarts fresh via `/watch-pr <work-item-id>`.

## Skills

- `use-context-file` — reading `working_branch`/`base_branch`/`worktree_path`/`worktree_branch`,
  recording `watch_worktree_path`/`watch_worktree_branch`, clearing the implement-phase fields
- `read-task-brief` — sourcing the brief/spec context `resolve-rebase-conflict` needs as its
  argument
- `workflow-worker` — the mediated spawn pattern (`--context-file`/`--write-section`/`--skill`/
  `--skill-args`) for nested `fix-pr` and `resolve-rebase-conflict` calls
