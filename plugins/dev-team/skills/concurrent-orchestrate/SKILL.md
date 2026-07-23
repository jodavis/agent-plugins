---
name: concurrent-orchestrate
user-invocable: false
description: >
  Orchestration loop for running several dependency-ordered task-work-items concurrently.
  Repeatedly invokes concurrent_schedule.py, spawns an isolated workflow-orchestrate run per
  newly eligible task, auto-starts a dev-team:watch-pr monitor the moment each one reaches
  hand-off, and stops on "complete" or "blocked" instead of polling forever.
argument-hint: --target-mode <up-to|list> --target <key, or comma-separated keys>
---

## Arguments

- `--target-mode` — `up-to` (inclusive dependency-closure target — its own dependency graph is
  expanded automatically) or `list` (an explicit task list — taken as-is, no closure expansion)
- `--target` — the single target key (`up-to` mode) or a comma-separated list of two or more
  keys (`list` mode)

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `concurrent_schedule.py` lives in this skill's own `scripts/` directory,
so it is invoked as `<skill-dir>/scripts/concurrent_schedule.py` — still anchored to
`<skill-dir>`, never to an assumed repo-root CWD.

## Configuration

### `concurrency.max-parallel-tasks` — integer

The repo-wide cap on concurrently active task-pipeline spawns, enforced internally by
`concurrent_schedule.py` (via `get-project-configuration`'s merged config) — never something
this skill's own prose reads or reasons about directly. Counts only active (non-terminal)
`workflow-orchestrate` spawns tracked across every `concurrent-<target-slug>.json` file under
this repo's state directory — never a `dev-team:watch-pr` monitor, which is idle almost all the
time it's running. Defaults to `3`; override in `.dev-team/config.yaml` for a machine with more
(or less) headroom for parallel agent sessions:

```yaml
concurrency:
  max-parallel-tasks: 5
```

## Role

You are the orchestration loop for running several task-work-items concurrently, all bounded
by one target set. You run as a single long-lived session that stays alive for the whole run —
not a `/loop`-style recurring re-invocation and not a scheduled/cron-triggered agent. You drive
the loop by invoking `concurrent_schedule.py` repeatedly, spawning whatever it tells you to,
and stopping on `"complete"` or `"blocked"`.

**Never attempt to:**
- Compute the dependency closure, a task's eligibility, or the concurrency cap yourself —
  `concurrent_schedule.py` owns all of that
- Fix build errors, test failures, or code review comments yourself
- Invoke agent skills directly (other than spawning `workflow-orchestrate` itself, unmodified,
  per task, and `dev-team:watch-pr` once that task reaches hand-off)
- Edit source files or test files
- Take any action beyond what the script's JSON descriptor instructs

## Steps

### 1 — Orchestration loop

Repeat the following until the script reports `"complete"` or `"blocked"`.

#### 1a — Run the scheduler script

```bash
python "<skill-dir>/scripts/concurrent_schedule.py" --up-to "<target>"
```

or, for the explicit-list form:

```bash
python "<skill-dir>/scripts/concurrent_schedule.py" --list "<target>"
```

Capture stdout — a single JSON object `{"status": ..., "spawn": [...], "blocked_tasks": [...]}`.
If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead — stop
and report that error in detail (a dangling/cyclic spec, or an explicit-list task whose
dependency is neither in the list nor already done); do not retry or fall back to guessing.

#### 1b — Branch on status

- **`"complete"`** — every task in the target set has reached hand-off and `spawn` is empty.
  Go to step 2 and stop.
- **`"blocked"`** — every currently-spawned task has also reached a terminal state, but some
  not-yet-started task's dependency chain includes a task that ended in `failed`, so it can
  never become eligible. Go to step 2 and stop — never keep polling once this fires.
- **`"waiting"`** — continue to step 1c for each entry in `spawn` (possibly empty this cycle:
  the cap is full, or nothing newly eligible), then to step 1d.

#### 1c — Spawn each newly eligible task

For each `{task_id, base_branch}` in `spawn`:

1. If `base_branch` is not `None`, use the `use-context-file` skill to write it to that task's
   context file's `base_branch` frontmatter field, before spawning — `ensure-working-branch`
   uses it directly instead of computing its own default when it finds it already set. If
   `base_branch` is `None`, do nothing: leave the field unset so `ensure-working-branch` falls
   through to its own existing default resolution (every dependency already merged, or no
   dependencies at all).
2. Spawn a fresh, isolated `workflow-orchestrate` run in the background, so this loop isn't
   blocked waiting on it before moving to the next task or the next poll:
   ```
   Agent(
     subagent_type: "claude",
     isolation: "worktree",
     run_in_background: true,
     prompt: "Invoke the `workflow-orchestrate` skill with arguments:
   --work-item-id <task_id> --workflow implement-task-plan --research-skill plan-task"
   )
   ```
3. Once the spawn call returns its worktree path and branch, use the `use-context-file` skill
   to record them into that task's context file as `worktree_path` / `worktree_branch` — the
   `Agent` tool only auto-cleans a worktree if the spawned agent made *no* changes, which never
   applies here, so this is what makes the worktree findable for cleanup later.

#### 1d — Wait, then re-invoke

Re-invoke the scheduler (step 1a) whenever either of these happens, whichever comes first:
- **60 seconds elapse** — a dependency merely reaching "PR open" mid-pipeline (the actual
  readiness gate for its dependents) is not a terminal event you're notified on, so periodic
  re-invocation is the only way to catch it.
- **Any spawned pipeline from step 1c finishes** — the harness notifies on background-agent
  completion; treat that notification as an immediate trigger both to re-invoke rather than
  waiting out the rest of the 60 seconds, and to run step 1e below for the task_id(s) that
  notification names.

#### 1e — Auto-start `dev-team:watch-pr` for a task that just reached hand-off

Keep your own in-session record of which task_ids you've already spawned a `dev-team:watch-pr`
monitor for (start empty; this record lives only in this session's own memory, never written to
any file — a restarted `concurrent-orchestrate` run has no spawned pipelines finishing anew for
an already-handed-off task, so it never re-triggers this step for one).

A spawned pipeline finishing successfully (step 1c's `workflow-orchestrate` `Agent` session
reporting success) means that task's own state machine transitioned `handoff → done` in one
pass — there is no separately observable "reached hand-off" event apart from that session
finishing successfully. For each task_id whose spawned pipeline the step 1d trigger just
reported as finished *successfully*, and that isn't already in your in-session record:

1. Use the `use-context-file` skill to read that task's context file and confirm `pr_url` is
   set (it always will be, on a successful hand-off — this is a sanity check, not a retry loop).
2. Spawn `dev-team:watch-pr` for it as a **local background `Agent`** (`run_in_background: true`,
   not a cloud routine), mirroring the exact spawn pattern step 1c already uses for
   `workflow-orchestrate` itself:
   ```
   Agent(
     subagent_type: "claude",
     isolation: "worktree",
     run_in_background: true,
     prompt: "Invoke the `watch-pr` skill with arguments:
   --work-item-id <task_id>"
   )
   ```
3. Add `task_id` to your in-session record so this task never gets a second monitor spawned for
   it, even if a later poll re-notices its pipeline as finished.

A pipeline that finished *unsuccessfully* (failed rather than handed off) never reaches this
step — there is no PR to monitor, so no `dev-team:watch-pr` is spawned for it.

### 2 — Report

- **`"complete"`** — tell the user every task in the target set reached hand-off.
- **`"blocked"`** — tell the user the run stopped, naming `blocked_tasks` and the reason (each
  one's dependency chain includes a task that ended in `failed`, so it can never become
  eligible on its own).

## Skills

- `use-context-file` — pre-populating `base_branch`, and recording `worktree_path` /
  `worktree_branch`, on a spawned task's context file
