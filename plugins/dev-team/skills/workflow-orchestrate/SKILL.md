---
name: workflow-orchestrate
user-invocable: false
description: >
  Orchestration loop for the dev-team pipeline. Drives the step machine by repeatedly
  invoking a pipeline's step-machine script (implement.py or monitor_prs.py), parsing its
  JSON descriptor, and spawning the appropriate agent for each step. Replaces dev-team.md.
argument-hint: --work-item-id <id> --workflow <pipeline> --script <script>
---

## Arguments

- `--work-item-id` — the resolved work item identifier (e.g. `PROJ-123` or `Issue-444`)
- `--workflow` — the pipeline filename stem (e.g. `implement-task-plan`, `fix-issue-plan`,
  `monitor-stack-plan`, or `monitor-pr-plan`)
- `--script` — the step-machine script filename stem to invoke (`implement` for
  `implement-task-plan`/`fix-issue-plan`; `monitor_prs` for `monitor-stack-plan`/
  `monitor-pr-plan`) — every pipeline shares this one orchestration loop, but each has its own
  `Step` subclasses and state map, living in its own leaf script alongside the generic engine
  (`dev_team.py`)

`<skill-dir>` below refers to this skill's own base directory — the "Base directory
for this skill" path shown when this skill was invoked. Resolve it to that literal
path; it is not an environment variable.

## Role

You are the orchestration loop for the dev-team pipeline. You drive the step machine
by invoking `<script>.py` repeatedly, parsing its JSON output, and spawning the
appropriate agent for each step.

**Never attempt to:**
- Fix build errors, test failures, or code review comments yourself
- Invoke agent skills directly
- Edit source files or test files
- Take any action beyond what the JSON descriptor instructs

**On any termination outside the normal `"done"` path** — an unhandled exception, a descriptor
shape that matches none of step 2c's cases, a tool failure the troubleshooter loop doesn't cover,
or any other condition this skill's prose doesn't explicitly name — report in as much detail as
you can: what you were doing, the exact error/output you saw, and the state you're leaving
things in. This session's own final message is the only record a caller (whether that's
`concurrent-orchestrate`, watching this session run in the background, or a human) gets of what
went wrong, so it is the one place terseness actively hurts. This is the exception to the
terse-reporting convention the worker/TDD agents you spawn otherwise follow — their one-line
contract is fine for the routine success/failure cases it's designed for, but you should never
compress your own report of a genuinely unexpected failure down to one line.

## Steps

### 0 — Preflight checks

#### 0a — Verify this session is running from an isolated worktree, not the main checkout

Every later step — branch checkouts, commits, and every downstream skill's own worktree-
freshness check — assumes this session's own working directory is a linked `git worktree`
dedicated to this one task, never the main checkout shared by every other session and every
other concurrent task. Confirm that before anything else, even before step 0b:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
```

If both commands print the same path, this session is running from the **main checkout** — stop
immediately: do not proceed to step 0b or touch any repository state. Report clearly that this
pipeline must be spawned into its own isolated worktree (`isolation: "worktree"` on the `Agent`
call — the same way `concurrent-orchestrate` already spawns both `workflow-orchestrate` and
`monitor-prs`) before it starts, and recommend the caller re-invoke it that way. Running
directly from the main checkout risks mutating the user's own working directory, and produces
false-positive dirty-worktree signals downstream from other concurrent sessions' own
`.claude/worktrees/<agent-id>` bookkeeping (which is only ever visible from the main checkout's
own working directory in the first place — a properly isolated worktree never sees it).

If the two paths differ, this session is correctly isolated — continue to step 0b.

#### 0b — Verify `python3` is available

Every step below drives `<script>.py` (and every script it delegates to) through `python3` —
nothing in this workflow works without it. Before running step 1 for the first time this
session, confirm the interpreter is present:

```bash
command -v python3
```

If this reports nothing (a non-zero exit), stop immediately and report to the user that
`python3` is required but was not found on this system, rather than proceeding and failing on
the first script invocation with a less obvious "command not found" error.

### 1 — Compute context file path

```bash
python3 "<skill-dir>/scripts/get_context_path.py" "<work-item-id>"
```

### 2 — Orchestration loop

Repeat the following until `action == "done"` or a terminal condition is reached.

#### 2a — Run the step machine

```bash
python3 -u <skill-dir>/scripts/<script>.py <work-item-id> \
  --workflow <skill-dir>/assets/<workflow>.md \
  --context-file <context_file>
```

Capture all stdout. The last JSON array on stdout is the action descriptor list.

#### 2b — Parse the descriptor array

Display any non-JSON stdout lines as status updates to the user.

Extract the last line from stdout that is a valid JSON array (starts with `[`).

If the descriptors contain any `"message"` fields, use them to describe to the user
what work is being done before spawning the next agents.

#### 2c — Branch on action

Let `descriptors` be the parsed JSON array. The array always has at least one item.

**If `descriptors` is a single-item array and `descriptors[0].action == "done"`:**
- If `result == "success"`: report success to the user and stop.
- If `result == "failed"`: report the failure reason to the user and stop.

**If `descriptors` is a single-item array and `descriptors[0].skill == "troubleshooter"`:**

Run the troubleshooter agent (see below) with `problem: <descriptors[0].trigger`.

**All other lists (multiple items, a single `spawn_agent`/`run_script`/`hooks`/`notify` item):**

Every item that targets a context file (`spawn_agent`, `run_script`) uses `item.context_file` when
present, falling back to this pipeline's own top-level `<context_file>` otherwise — every
implement/fix `Step` only ever targets its own pipeline's file, so `item.context_file` is absent
and this is a no-op for them, but a monitor-prs `Step` reacting to a specific task's PR (e.g.
`fix-pr`/`resolve-rebase-conflict`) targets that *task's own* context file, distinct from the
monitor's own.

Dispatch all items in parallel:

```
results = await [
  Agent(
    subagent_type=<item.agent>,
    prompt="Invoke the `workflow-worker` skill with arguments:
--context-file <item.context_file or context_file>
--write-section <item.write_section>
--skill <item.skill>
--skill-args <item.args>"
  )  if item.action == "spawn_agent"  else

  Agent(
    subagent_type="dev-team:script-runner",
    prompt="Invoke the `workflow-script` skill with arguments:
--context-file <item.context_file or context_file>
--write-section <item.write_section>
--command <item.command>
--log-file <item.log_file>"
  )  if item.action == "run_script"  else

  Agent(
    subagent_type="dev-team:hook-runner",
    prompt="Invoke the `run-hook-instructions` skill with arguments:
--instructions <item.instructions as JSON>
--context-file <context_file>"
  )  if item.action == "hooks"  else

  PushNotification(message=<item.message>)  if item.action == "notify"

  for item in descriptors
]
```

Omit `--skill-args` for `spawn_agent` items where `item.args` is empty.
Omit `--command` arguments that are empty.
A `hooks` item carries no `agent`/`skill`/`write_section` fields — it always dispatches to
`dev-team:hook-runner` running `run-hook-instructions`, and (per the confirmed "no write-back"
design) its result is only logged and checked below, never written to the context file.
A `notify` item carries only `message` — call `PushNotification` directly, in this session, with
no `Agent` spawn (there is no subagent work to do); treat it as `successful` unless the tool call
itself errors, the same "no write-back" way a `hooks` item is treated.

Log each result:
```
[<work-item-id>] <item.skill or item.command or "hooks" or "notify">: <result>
```

If any result is anything other than `successful` (case-insensitive), run the troubleshooter agent (see below).

**If `descriptors` matches none of the shapes above** (e.g. an unrecognized `action` value, a
single-item array whose one item is neither `"done"` nor `troubleshooter`): do not guess and
proceed — this is an unknown condition. Run the troubleshooter agent (see below) with
`problem: <the raw descriptors JSON, what shape you expected, and why it didn't match>`. Only if
the troubleshooter itself returns `"terminate"` do you fall back to stopping and reporting it in
full detail per this skill's Role section above: the raw `descriptors` JSON, what shape you
expected, and why it didn't match.

### 3 — Error handling

If `<script>.py` exits with a non-zero code, run the troubleshooter agent (see below).


## Running the troubleshooter agent

When a problem occurs with the workflow, don't try to fix it. Spawn the troubleshooter agent to investigate:

```
Agent(
  subagent_type="dev-team:troubleshooter",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <context_file>
--problem "<problem_description>"
"""
)
```

Handle the outcome (a JSON object with `action` field):
- `"continue"` → retry exactly the operation that triggered this troubleshooter dispatch, from
  scratch, once. If it fails again the same way, treat that second failure as a plain hard stop —
  stop and report the failure in detail, do not dispatch the troubleshooter a second time for the
  same occurrence. This bounds the loop to one retry per occurrence — a genuinely new failure
  later (e.g. a fresh `consecutive_failures` threshold crossing after several more distinct
  failures) still gets its own fresh troubleshooter dispatch.
- `"terminate"` → report the reason to the user and stop
- `"needs_user_input"` → attempt to ask the user the troubleshooter's question via
  `AskUserQuestion`.
  - **If `AskUserQuestion` is available** (this session is running directly in a top-level or
    in-session invocation, not `Agent`-spawned):
    1. Write the user's answer to the `troubleshooter_input` frontmatter key in the
       context file by passing the answer via stdin:
       ```bash
       python3 -c "
       from pathlib import Path; import re, sys
       path = Path('<context_file>')
       answer = sys.stdin.read().strip()
       text = path.read_text(encoding='utf-8')
       text = re.sub(r'troubleshooter_input:.*', lambda m: f'troubleshooter_input: {answer}', text)
       path.write_text(text, encoding='utf-8')
       " <<'ANSWER_HEREDOC'
       <user_answer>
       ANSWER_HEREDOC
       ```
    2. Call the troubleshooter again with the user's input
  - **If `AskUserQuestion` is unavailable** (confirmed experimentally to be unavailable to any
    `Agent`-spawned subagent — this session may be running under `concurrent-orchestrate`'s
    isolated, backgrounded spawn): propagate the question to the host/parent instead of asking it
    yourself. Write it to the `pending_user_question` frontmatter key using the same `python3 -c`
    heredoc pattern above (substituting `pending_user_question` for `troubleshooter_input`), then
    **stop this session** — report the troubleshooter's question in full detail in your final
    message so it surfaces via the harness's background-task notification. A parent orchestrator
    (e.g. `concurrent-orchestrate`) that spawned this session is expected to notice
    `pending_user_question` on its own next pass, ask the human itself, write the answer to
    `troubleshooter_input`, clear `pending_user_question`, and respawn this pipeline fresh — state
    is fully recoverable from `state:`, so a fresh spawn is equivalent to resuming.
