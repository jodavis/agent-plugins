---
name: workflow-worker
user-invocable: false
description: >
  **Defines the rules for working as a part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run as an orchestrated worker.
argument-hint: --context-file <path> --write-section <section> --skill <skill> [--skill-args <args>] --todo-log <path>
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write output to (e.g. `Researcher Brief`)
- `--skill` — name of the skill to invoke
- `--skill-args` — (optional) arguments to pass to the skill
- `--todo-log` — absolute path to the shared todo log file for this work item

`<skill-dir>` below refers to this skill's own base directory — the "Base directory
for this skill" path shown when this skill was invoked. Resolve it to that literal
path; it is not an environment variable.

## Steps

### 1 — Redirect todo list tracking to the log file

Your agent role's instructions say to track planned work with `TodoWrite`. In this
orchestrated context, do not call `TodoWrite` directly — the orchestrator owns the
visible todo list and mirrors your updates into it.

Instead, every time you would have called `TodoWrite`, append one line to `<todo-log>`
containing exactly the JSON payload you would have passed to `TodoWrite` (e.g.
`{"todos": [...]}`), via this script (piping the payload through stdin, not a shell
argument, avoids quoting failures when the todo content contains apostrophes or quotes):

```bash
python "<skill-dir>/scripts/append_todo_log.py" "<todo-log>" <<'EOF'
<todo-write-json>
EOF
```

Always append, never truncate or rewrite the file — other agents may be sharing it
concurrently. Write one complete, self-contained JSON object per line so the
orchestrator can act on each line independently.

**Do not log a todo item for invoking the skill in step 2 itself** (e.g. "Invoke
plan-task skill"). That action is implicit in this workflow step, not meaningful
progress — it would just add noise to the visible todo list.

This exception covers only that one entry-point item. It is not permission to skip todo
tracking for the rest of the task — once the invoked skill's own work begins, break it
into concrete steps and log each one via step 1 exactly as you would without this
exception. A run that logs nothing but the skill invocation (or logs nothing at all) has
misapplied this exception.

### 2 — Invoke the skill

Use the `Skill` tool to invoke `<skill>` with `<skill-args>` as arguments. Follow the skill's
instructions and complete all its steps, applying the todo-log redirection from step 1
wherever the skill or your role would otherwise call `TodoWrite`. Capture the output —
do not return it to the caller yet.

### 3 — Write output to the context file

Write the captured output to the `<write-section>` section of `<context-file>`.
Use `Edit`, never `Write` — concurrent agents share this file and `Write` would overwrite their sections.

The section format is:
```
<!-- section:<write-section> -->

<content>
```

**If the sentinel `<!-- section:<write-section> -->` already exists:** use `Edit` to replace all
content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last
line of the file.

### 4 — Return status

Return exactly one of:
- `successful` — if the skill completed and its output was written to the context file
- A detailed description of the failure — if any step failed

**Never return intermediate messages, skill output, or anything else.** All output goes to the context file only.