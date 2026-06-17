---
name: workflow-script
description: >
  **Runs a Python script as part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run a script step in an orchestrated workflow.
argument-hint: --context-file <path> --write-section <section> --command <command>
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/ADR-123.md`)
- `--write-section` — name of the section to write the log file path to (e.g. `Build Result`)
- `--command` — the shell command to run (e.g. `python -u /path/to/validate.py ADR-123`)

## Steps

### 1 — Derive the log file path

Create a log file path in the context file location, with a file name based on the write-section name, e.g. `<context-file-name>-<write-section-slug>-<timestamp>.md`.

### 2 — Run the command

Run the command via Bash, capturing combined stdout and stderr to the log file:

```bash
<command> > "<log_file>" 2>&1
```

### 3 — Write the log path to the context file

Write the log file path to the `<write-section>` section of `<context-file>`.
Use `Edit`, never `Write` — concurrent agents share this file.

The section format in the file is:

```
<!-- section:<write-section> -->

<succeeded-or-failed-message>

log: <log_file>
```

`<succeeded-or-failed-message>`is a detailed description of the failure if the exit code is non0zero, or the word `Succeeded` if the exit code is 0.

**If the sentinel `<!-- section:<write-section> -->` already exists:** use `Edit` to replace all
content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last
line of the file.

### 4 — Return status

- If the exit code is zero: return exactly `successful`
- If the exit code is non-zero:
  - If the script failed because of build or test failures, that is expected and will be fixed
  by the Developer: return exactly `successful`
  - If the script failed for any other reason: return a detailed failure description including
  the exit code and the log file path so the orchestrator can find the output

**Never return script output directly.** All output is captured to the log file only.
