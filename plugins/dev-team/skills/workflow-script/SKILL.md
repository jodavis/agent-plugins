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

Compute the log file path from the context file location and the write-section name:

```bash
log_dir=$(dirname "<context-file>")
stem=$(basename "<context-file>" .md)
section_slug=$(echo "<write-section>" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-')
log_file="${log_dir}/${stem}-${section_slug}.log"
```

### 2 — Run the command

Run the command via Bash, capturing combined stdout and stderr to the log file:

```bash
<command> > "<log_file>" 2>&1
exit_code=$?
```

### 3 — Write the log path to the context file

Write the log file path to the `<write-section>` section of `<context-file>`.
Use `Edit`, never `Write` — concurrent agents share this file.

The section format in the file is:

```
<!-- section:<write-section> -->

log: <log_file>
```

**If the sentinel `<!-- section:<write-section> -->` already exists:** use `Edit` to replace all
content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last
line of the file.

### 4 — Return status

- If `exit_code` is `0`: return exactly `successful`
- If `exit_code` is non-zero: return a detailed failure description including the exit code and
  the log file path so the orchestrator can find the output

**Never return script output directly.** All output is captured to the log file only.
