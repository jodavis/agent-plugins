---
name: workflow-orchestrate
user-invocable: false
description: >
  Orchestration loop for the dev-team pipeline. Drives the step machine by repeatedly
  invoking dev_team.py, parsing its JSON descriptor, and spawning the appropriate
  agent for each step. Replaces dev-team.md.
argument-hint: --work-item-id <id> --workflow <pipeline> --research-skill <skill>
---

## Arguments

- `--work-item-id` — the resolved work item identifier (e.g. `PROJ-123` or `Issue-444`)
- `--workflow` — the pipeline filename stem (e.g. `implement-task-plan` or `fix-issue-plan`)
- `--research-skill` — the researcher skill name (e.g. `plan-task` or `researcher-issue`)

`<skill-dir>` below refers to this skill's own base directory — the "Base directory
for this skill" path shown when this skill was invoked. Resolve it to that literal
path; it is not an environment variable.

## Role

You are the orchestration loop for the dev-team pipeline. You drive the step machine
by invoking `dev_team.py` repeatedly, parsing its JSON output, and spawning the
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

### 0 — Verify `python3` is available

Every step below drives `dev_team.py` (and every script it delegates to) through `python3` —
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
python3 -u <skill-dir>/scripts/dev_team.py <work-item-id> \
  --workflow <skill-dir>/assets/<workflow>.md \
  --research-skill <research-skill> \
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

**All other lists (multiple items, a single `spawn_agent` item, or a single `run_script` item):**

Dispatch all items in parallel:

```
results = await [
  Agent(
    subagent_type=<item.agent>,
    prompt="Invoke the `workflow-worker` skill with arguments:
--context-file <context_file>
--write-section <item.write_section>
--skill <item.skill>
--skill-args <item.args>
--event <item.event>"
  )  if item.action == "spawn_agent"  else

  Agent(
    subagent_type="dev-team:script-runner",
    prompt="Invoke the `workflow-script` skill with arguments:
--context-file <context_file>
--write-section <item.write_section>
--command <item.command>
--log-file <item.log_file>
--event <item.event>"
  )  if item.action == "run_script"

  for item in descriptors
]
```

Omit `--skill-args` for `spawn_agent` items where `item.args` is empty.
Omit `--command` arguments that are empty.
Omit `--event` entirely for either item type when `item.event` is absent.

Log each result:
```
[<work-item-id>] <item.skill or item.command>: <result>
```

If any result is anything other than `successful` (case-insensitive), run the troubleshooter agent (see below).

**If `descriptors` matches none of the shapes above** (e.g. an unrecognized `action` value, a
single-item array whose one item is neither `"done"` nor `troubleshooter`): do not guess and
proceed — this is an unknown condition. Stop and report it in full detail per this skill's Role
section above: the raw `descriptors` JSON, what shape you expected, and why it didn't match.

### 3 — Error handling

If `dev_team.py` exits with a non-zero code, run the troubleshooter agent (see below).


## Running the troubleshooter agent

When a problem occurs with the workflow, don't try to fix it. Spawn the troubleshooter agent to investigate:

```
Agent(
  subagent_type="claude",
  prompt="""Invoke the `dev-team:workflow-troubleshoot` skill with arguments:
--context-file <context_file>
--problem "<problem_description>"
"""
)
```

Handle the outcome (a JSON object with `action` field):
- `"continue"` → continue the loop (the troubleshooter has edited the context file)
- `"terminate"` → report the reason to the user and stop
- `"needs_user_input"` →
  1. Ask the user the troubleshooter's question
  2. Write the user's answer to the `troubleshooter_input` frontmatter key in the
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
  3. Call the troubleshooter again with the user's input
