## PR mode

Reached when `--pr-numbers <pr1>[,<pr2>...]` was given — see "Determining which mode to run"
above. Always a direct, in-session `/watch-pr` invocation (there is no auto-started, isolated-
worktree path for PR mode — `concurrent-orchestrate` only ever auto-starts stack mode), so there
is no worktree-freshness check and no fresh-worktree bootstrap to do here, mirroring stack mode's
step 2b exactly: this monitor runs from whatever worktree the user already put it in, and never
allocates or later needs to clean up one of its own.

### 1 — Poll loop

Repeat the following indefinitely, until 1b's `"all_complete"` case stops you.

#### 1a — Poll

```bash
python3 "<skill-dir>/../workflow-orchestrate/scripts/pr_list_poll.py" <pr-numbers, comma-separated>
```

Pass `--pr-numbers`'s value straight through as the first positional argument — `pr_list_poll.py`
takes the same comma-separated format. Its only other argument is an optional positional
`max_seconds` bound (default 480); this skill never needs to override it.

Parse stdout as JSON. It is exactly one of: `"all_complete"`, `"no_change"`, or
`{"task_work_item_id": ..., "event": "review_comment" | "human_comment" | "ci_failure"}` — never
`"conflict"` (PR mode has no `gh stack` cascade to conflict) and never a batch.

If `"no_change"`, go straight back to 1a — `pr_list_poll.py` already blocked internally for its
own bounded window; no additional wait is needed here.

If the script exits non-zero, it prints a clear `Error: ...` message to stderr instead of JSON —
this is a **hard stop**: stop immediately and report that error in detail. Unlike stack mode's
equivalent failures, there is no context file naturally in hand yet at this point to route
through the troubleshooter (PR mode has no epic, and this failure isn't about any one PR in
particular) — see "Running the troubleshooter agent" below for the one PR-mode case that *does*
route through it.

#### 1b — React to exactly the one outcome returned

- **`"all_complete"`** — every given PR has merged. Report success and stop: there is no
  worktree of this monitor's own to clean up (see this section's own intro above).
- **`{"task_work_item_id", "event": "review_comment" | "ci_failure"}`** — a review comment or CI
  failure fired for that PR. `pr_list_poll.py` has already checked out that PR's own branch
  itself — no checkout of your own is needed. Use the `use-context-file` skill to compute that
  task's own context file path (`<task_context_file>`), then spawn `fix-pr` against it (nested,
  via the developer agent):
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
  `Post-Handoff Fix <n>` is a section name on that task's own context file — start `<n>` at 1 for
  this run and increment it for each such spawn, regardless of which PR it's for (one counter for
  the whole PR-mode session, not one per PR). If the spawn reports anything other than
  `successful`, run the troubleshooter agent (see "Running the troubleshooter agent" below,
  PR-mode case) with problem `"monitor-prs PR mode: fix-pr spawn for task <task_work_item_id>
  reported <status>"` — do not retry automatically yourself. Otherwise, return to 1a.
- **`{"task_work_item_id", "event": "human_comment"}`** — someone other than this pipeline's own
  automation account posted a new PR comment. This needs a personal response, not an automatic
  fix — **never spawn `fix-pr` for this event**. Use the `use-context-file` skill to compute that
  task's own context file path (`<task_context_file>`) and read `pr_url` from it, then call
  `PushNotification` with a message naming the task and PR, e.g. `"Human comment on
  <task_work_item_id>'s PR needs a response: <pr_url>"`. Return to 1a immediately afterward — do
  not stop this agent.
- **`"no_change"`** — return to 1a immediately.

## Running the troubleshooter agent

Several points above say to "run the troubleshooter agent" for a specific problem string, instead
of stopping outright — just like `workflow-orchestrate` and `concurrent-orchestrate` do for their
own pipeline anomalies, this keeps the actual debugging investigation, and any bug it files,
out of the top-level session's own context. The context file passed along differs by mode, since
the two modes have different bookkeeping records available:

**Stack mode** — every point that dispatches the troubleshooter is reached after step 2 has
resolved the epic's own context file, so it's always available to pass along:

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <epic's own context file, resolved in step 2>
--problem "<the problem string that point named>"
"""
)
```

Step 1's worktree-freshness hard stop, and step 2b's own epic-derivation hard stop (a usage
issue, not a pipeline bug: the current branch itself has no recorded epic to derive one from),
both stay plain hard stops regardless — neither has an epic context file in hand yet.

**PR mode** — there is no epic context file at all in this mode. The only point that dispatches
the troubleshooter (1b's fix-pr spawn failure) already has the *relevant task's own* context
file in hand — pass that instead:

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <task_context_file, computed in 1b>
--problem "<the problem string that point named>"
"""
)
```

`pr_list_poll.py` itself failing (1a) has no single task's context file naturally in hand — that
case stays a plain hard stop rather than manufacturing a context file to hand the troubleshooter.

**Handling the outcome is identical in both modes** (a JSON object with an `action` field):
- `"continue"` — the troubleshooter applied a fix. Retry exactly the operation that triggered this
  dispatch, from scratch, once. If it fails again the same way, treat that second failure as a
  plain hard stop — stop and report the failure in detail, do not dispatch the troubleshooter a
  second time for the same occurrence. This bounds the loop to one retry per occurrence.
- `"terminate"` — report the reason to the user and stop this agent entirely, the same as any
  other hard stop.
- `"needs_user_input"` — `AskUserQuestion` is unavailable here (see "Never attempt to" above);
  stop and report the troubleshooter's question in detail so it surfaces via the harness's
  background-task notification, the same way stack mode's step 5 `"unresolved"` case does. A
  human answers by writing the answer to the context file's `troubleshooter_input` field (the
  same mechanism `concurrent-orchestrate`'s own troubleshooter handling documents) and resuming
  this same agent via `SendMessage`.

