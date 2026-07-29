---
name: workflow-worker
user-invocable: false
description: >
  **Defines the rules for working as a part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run as an orchestrated worker.
argument-hint: --context-file <path> --write-section <section> --skill <skill> [--skill-args <args>]
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write output to (e.g. `Researcher Brief`)
- `--skill` — name of the skill to invoke
- `--skill-args` — (optional) arguments to pass to the skill

`<skill-dir>` below refers to this skill's own base directory — the "Base directory
for this skill" path shown when this skill was invoked. Resolve it to that literal
path; it is not an environment variable.

## Steps

### 1 — Invoke the skill

Use the `Skill` tool to invoke `<skill>` with `<skill-args>` as arguments. Follow the skill's
instructions and complete all its steps. Capture the output — do not return it to the caller
yet.

**Note on nested "return" instructions:** `<skill>`'s own final step often says something like
"Return the brief as prose" or "Return your findings." That wording is written for when the skill
is invoked standalone, with no wrapping contract. It is not an instruction to end your turn here.
When you are running under workflow-worker, treat that final instruction only as marking the
content to capture — do not send it as your own final message, and do not stop. Always continue
on to step 2 and step 3 below.

### 2 — Write output to the context file

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

### 3 — Return status

Return exactly one of:
- `successful` — if the skill completed and its output was written to the context file
- A detailed description of the failure — if any step failed

**Never return intermediate messages, skill output, or anything else.** All output goes to the context file only.