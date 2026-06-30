---
name: workflow-worker
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

## Steps

### 1 — Redirect todo list tracking to the log file

Your agent role's instructions say to track planned work with `TodoWrite`. In this
orchestrated context, do not call `TodoWrite` directly — the orchestrator owns the
visible todo list and mirrors your updates into it.

Instead, every time you would have called `TodoWrite`, append one line to `<todo-log>`
containing exactly the JSON payload you would have passed to `TodoWrite` (e.g.
`{"todos": [...]}`), via Bash:

```bash
echo '<todo-write-json>' >> "<todo-log>"
```

Always append (`>>`), never truncate or rewrite the file — other agents may be sharing
it concurrently. Write one complete, self-contained JSON object per line so the
orchestrator can act on each line independently.

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