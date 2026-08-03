---
name: concurrent-orchestrate
user-invocable: false
description: >
  Orchestration loop for running several dependency-ordered task-work-items concurrently.
  Repeatedly invokes concurrent_schedule.py, spawns an isolated workflow-orchestrate run per
  newly eligible task, auto-starts a dev-team:monitor-pr monitor the moment each one reaches
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
this repo's state directory — never a `dev-team:monitor-pr` monitor, which is idle almost all the
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
  per task, and `dev-team:monitor-pr` once that task reaches hand-off)
- Edit source files or test files
- Take any action beyond what the script's JSON descriptor instructs

## Steps

### 0 — Verify `python3` is available

Every step below drives `concurrent_schedule.py` (and, transitively, every spawned
`workflow-orchestrate` run) through `python3` — nothing in this pipeline works without it.
Before running step 1 for the first time this session, confirm the interpreter is present:

```bash
command -v python3
```

If this reports nothing (a non-zero exit), stop immediately and report to the user that
`python3` is required but was not found on this system, rather than proceeding and failing on
the first script invocation with a less obvious "command not found" error.

### 1 — Reconcile against what's already running

Run once before entering the main loop (step 2) — the first thing this session does whether
it's a brand-new run or one resuming after a restart. A restart orphans whatever
`workflow-orchestrate` spawns were in flight: this session has no memory of them, and nothing
will ever notify it that they finished, so left unchecked they'd sit silently stalled forever.
This step detects that and respawns.

1. Take one non-blocking snapshot — `--max-poll-cycles 0` is a new invocation mode, distinct
   from step 2a's default ~5-minute polling behavior, that returns after exactly one poll
   instead of blocking until something becomes actionable:
   ```bash
   python3 "<skill-dir>/scripts/concurrent_schedule.py" --up-to "<target>" --max-poll-cycles 0
   ```
   or the `--list` form, matching whichever target mode this run uses.
2. For each `{task_id, status, last_updated, worktree_path}` entry in the returned `running`
   list, check whether this session already holds a live spawn handle for it — i.e. whether this
   session itself spawned it via step 2c, in this run or an earlier one before a restart. Keep
   this record only in this session's own memory, never written to any file, mirroring step 2e's
   own in-session record. A freshly started session holds none, so in practice every entry in
   this first snapshot is unclaimed; only a session resuming mid-run (rather than after a
   restart) would already track some.
3. For each unclaimed entry, judge it by `last_updated`: if more than 15 minutes have elapsed
   since it was last written, treat it as stalled — its `workflow-orchestrate` spawn silently
   died or its session was lost — and respawn `workflow-orchestrate` for it exactly the way step
   2c does. It's reentrant and resumes from the task's recorded `state`, so respawning a task
   that's actually still healthy, or one that already reached hand-off, is harmless. Record the
   respawn the same way step 2c does, so this session tracks it as its own from here on.
   Otherwise, leave it alone — it's within its expected staleness window.

Continue to step 2 once every entry in the snapshot has been checked.

### 2 — Orchestration loop

Repeat the following until the script reports `"complete"` or `"blocked"`.

#### 2a — Run the scheduler script

```bash
python3 "<skill-dir>/scripts/concurrent_schedule.py" --up-to "<target>"
```

or, for the explicit-list form:

```bash
python3 "<skill-dir>/scripts/concurrent_schedule.py" --list "<target>"
```

The script blocks internally rather than returning the instant it sees nothing to do.
Invoke this `Bash` call with an explicit `timeout` of at least `330000`
(5.5 minutes) — comfortably past the script's own ~5-minute default polling budget.

Capture stdout — a single JSON object
`{"status": ..., "spawn": [...], "blocked_tasks": [...], "running": [...]}`. If the script exits
non-zero, it prints a clear `Error: ...` message to stderr instead — stop and report that error
in detail (a dangling/cyclic spec, or an explicit-list task whose dependency is neither in the
list nor already done); do not retry or fall back to guessing.

#### 2b — Branch on status

- **`"complete"`** — every task in the target set has reached hand-off and `spawn` is empty.
  Go to step 3 and stop.
- **`"blocked"`** — every currently-spawned task has also reached a terminal state, but some
  not-yet-started task's dependency chain includes a task that ended in `failed`, so it can
  never become eligible. Go to step 3 and stop — never keep polling once this fires.
- **`"waiting"`** — continue to step 2c for each entry in `spawn` (possibly empty this cycle:
  the cap is full, or nothing newly eligible), then to step 2d.

#### 2c — Spawn each newly eligible task

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
4. Add `task_id` to this session's own in-session "live spawn handle" record — the same one
   steps 1 and 2d check before treating a `running` entry as unclaimed. Keep it only in this
   session's own memory, never written to any file, mirroring step 2e's own in-session record.
   This is what makes steps 1 and 2d's "not already held" check meaningful instead of vacuously
   true forever.

#### 2d — Wait, then re-invoke

If step 2c just spawned anything, or a spawned pipeline's completion notification is already
sitting in front of you, re-invoke the scheduler (step 2a) right away — no extra pause needed,
since the script's own internal polling (step 2a) already paces repeat calls for you.

Otherwise — step 2a returned `"waiting"` with an empty `spawn`, meaning its own internal ~5
minutes of polling turned up nothing new — use this natural pause to sanity-check that
previously spawned pipelines still look healthy. Apply the same staleness check step 1 uses: for
each entry in the most recent poll's `running` list that this session holds a live spawn handle
for, if more than 15 minutes have elapsed since its `last_updated`, treat it as a stall
discovered mid-run — its `workflow-orchestrate` spawn died silently without ever reporting
completion — and respawn `workflow-orchestrate` for it exactly the way step 2c does, catching the
stall immediately rather than waiting for a restart to trigger step 1's own reconciliation. If
everything else looks healthy, wait 30 seconds and re-invoke step 2a again. If something else
looks broken (not covered by the staleness check), invoke a troubleshooting step rather than
continuing to poll blindly.

Either way, **any spawned pipeline from step 2c finishing** — reported to you as a background-
agent completion notification, whether it arrives between cycles or while step 2a's `Bash` call
is still in flight (in which case you'll see it as soon as that call returns) — is always the
trigger to run step 2e below for the task_id(s) it names, in addition to whatever re-invocation
timing applies above.

#### 2e — Auto-start `dev-team:monitor-pr` for a task that just reached hand-off

Keep your own in-session record of which task_ids you've already spawned a `dev-team:monitor-pr`
monitor for (start empty; this record lives only in this session's own memory, never written to
any file — a restarted `concurrent-orchestrate` run has no spawned pipelines finishing anew for
an already-handed-off task, so it never re-triggers this step for one).

A spawned pipeline finishing successfully (step 2c's `workflow-orchestrate` `Agent` session
reporting success) means that task's own state machine transitioned `handoff → done` in one
pass — there is no separately observable "reached hand-off" event apart from that session
finishing successfully. For each task_id whose spawned pipeline the step 2d trigger just
reported as finished *successfully*, and that isn't already in your in-session record:

1. Use the `use-context-file` skill to read that task's context file and confirm `pr_url` is
   set (it always will be, on a successful hand-off — this is a sanity check, not a retry loop).
   If `pr_url` is empty, do not spawn a monitor for this task_id: skip it, report the
   inconsistency in detail (task_id and the fact that a successful hand-off left no `pr_url`),
   and add it to the in-session record anyway so a later poll doesn't repeatedly re-report the
   same inconsistency for it.
2. Spawn `dev-team:monitor-pr` for it as a **local background `Agent`** (`run_in_background: true`,
   not a cloud routine), mirroring the exact spawn pattern step 2c already uses for
   `workflow-orchestrate` itself:
   ```
   Agent(
     subagent_type: "claude",
     isolation: "worktree",
     run_in_background: true,
     prompt: "Invoke the `monitor-pr` skill with arguments:
   --work-item-id <task_id>"
   )
   ```
3. Add `task_id` to your in-session record so this task never gets a second monitor spawned for
   it, even if a later poll re-notices its pipeline as finished.

A pipeline that finished *unsuccessfully* (failed rather than handed off) never reaches this
step — there is no PR to monitor, so no `dev-team:monitor-pr` is spawned for it.

### 3 — Report

- **`"complete"`** — tell the user every task in the target set reached hand-off.
- **`"blocked"`** — tell the user the run stopped, naming `blocked_tasks` and the reason (each
  one's dependency chain includes a task that ended in `failed`, so it can never become
  eligible on its own).

## Skills

- `use-context-file` — pre-populating `base_branch`, and recording `worktree_path` /
  `worktree_branch`, on a spawned task's context file
