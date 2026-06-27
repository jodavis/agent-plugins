---
name: workflow-script
description: >
  **Runs a Python script as part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run a script step in an orchestrated workflow.
argument-hint: --context-file <path> --write-section <section> --command <command> --log-file <log_file>
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write the log file path to (e.g. `Build Result`)
- `--command` — the shell command to run (e.g. `python -u /path/to/validate.py PROJ-123`)
- `--log-file` — a full path to a location where the script's output should be logged 

## Steps

### 1 — Run the command

Run the command via Bash, capturing combined stdout and stderr to the log file:

```bash
<command> > "<log_file>" 2>&1
```

### 2 — Write the log path to the context file

Write the log file path to the `<write-section>` section of `<context-file>`.
Use `Edit`, never `Write` — concurrent agents share this file.
_Do not touch any other part of the file, and never modify the YAML
frontmatter unless explicitly instructed to do so._

The section format in the file is:

```
<!-- section:<write-section> -->

<result>

log: <log_file>
```

Determine `<result>` as follows:

1. Read the last non-empty line of the log file.
2. If that line is a valid JSON object (starts with `{` and ends with `}`), use it verbatim as
   `<result>` — regardless of exit code. This lets scripts communicate structured status.
3. Otherwise: use `Succeeded` if the exit code is 0, or a short failure description (including
   the exit code) if non-zero.

**If the sentinel `<!-- section:<write-section> -->` already exists:** use `Edit` to replace all
content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last
line of the file.

### 3 — Return status

- If the exit code is zero: return exactly `successful`
- If the exit code is non-zero:
  - If the script failed because of build or test failures, that is expected and will be fixed
  by the Developer: return exactly `successful`
  - If the script failed for any other reason: return a detailed failure description including
  the exit code and the log file path so the orchestrator can find the output

**Never return script output directly.** All output is captured to the log file only.
