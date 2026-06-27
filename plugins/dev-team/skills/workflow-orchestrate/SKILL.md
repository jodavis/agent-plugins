---
name: workflow-orchestrate
description: >
  Orchestration loop for the dev-team pipeline. Drives the step machine by repeatedly
  invoking dev_team.py, parsing its JSON descriptor, and spawning the appropriate
  agent for each step. Replaces dev-team.md.
argument-hint: --work-item-id <id> --workflow <pipeline> --research-skill <skill>
---

## Arguments

- `--work-item-id` — the resolved work item identifier (e.g. `PROJ-123` or `Issue-444`)
- `--workflow` — the pipeline filename stem (e.g. `implement-task-plan` or `fix-issue-plan`)
- `--research-skill` — the researcher skill name (e.g. `researcher-plan` or `researcher-issue`)

## Role

You are the orchestration loop for the dev-team pipeline. You drive the step machine
by invoking `dev_team.py` repeatedly, parsing its JSON output, and spawning the
appropriate agent for each step.

**Never attempt to:**
- Fix build errors, test failures, or code review comments yourself
- Invoke agent skills directly
- Edit source files or test files
- Take any action beyond what the JSON descriptor instructs

## Steps

### 1 — Compute context file path

```bash
"$SKILL_DIR/scripts/get-context-path.sh" "<work-item-id>"
```

### 2 — Orchestration loop

Repeat the following until `action == "done"` or a terminal condition is reached.

#### 2a — Run the step machine

```bash
python -u $SKILL_DIR/scripts/dev_team.py <work-item-id> \
  --workflow $SKILL_DIR/assets/<workflow>.md \
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
--skill-args <item.args>"
  )  if item.action == "spawn_agent"  else

  Agent(
    subagent_type="dev-team:script-runner",
    prompt="Invoke the `workflow-script` skill with arguments:
--context-file <context_file>
--write-section <item.write_section>
--command <item.command>
--log-file <item.log_file>"
  )  if item.action == "run_script"

  for item in descriptors
]
```

Omit `--skill-args` for `spawn_agent` items where `item.args` is empty.
Omit `--command` arguments that are empty.

Log each result:
```
[<work-item-id>] <item.skill or item.command>: <result>
```

If any result is anything other than `successful` (case-insensitive), run the troubleshooter agent (see below).

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
     python -c "
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
