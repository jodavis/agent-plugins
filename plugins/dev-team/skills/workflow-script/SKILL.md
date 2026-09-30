---
name: workflow-script
user-invocable: false
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write the log file path to (e.g. `Build Result`)
- `--command` — the shell command to run (e.g. `python3 -u /path/to/validate.py PROJ-123`)
- `--log-file` — a full path to a location where the script's output should be logged

## Steps

### 1 — Run the command

Run the command via Bash, capturing combined stdout and stderr to the log file:

```bash
<command> > "<log_file>" 2>&1
```

### 2 — Determine the result

1. Read the last non-empty line of the log file.
2. If that line is a valid JSON object (starts with `{` and ends with `}`), use it verbatim as
   `<result>` — regardless of exit code. This lets scripts communicate structured status.
3. Otherwise: use `Succeeded` if the exit code is 0, or a short failure description (including
   the exit code) if non-zero.

### 3 — Write the result to the context file

Use the `write-scratch-deliverable` skill to persist the result — do not edit `<context-file>`
yourself, with `Edit` or otherwise; concurrent agents share it, and a direct edit here has no way
to guarantee the exact byte-for-byte `<result>` from step 2 actually lands (a freehand edit can
silently reword, summarize, or drop it — the same failure mode `workflow-worker` moved off of
for this same reason).

`<work-item-id>` (needed by `write-scratch-deliverable`'s own step 1) is `<context-file>`'s own
filename without the `.md` extension — context files are always named `<work-item-id>.md`.

Compose the deliverable content exactly as:
```
<result>

log: <log_file>
```

`dev_team.py`'s `merge_pending_deliverables()` picks up the scratch file and merges it into
`<context-file>`'s `<write-section>` section on the next orchestration-loop iteration.

### 4 — Return status

- If the exit code is zero: return `successful`
- If the exit code is non-zero:
  - If the script failed because of build or test failures, that is expected and will be fixed
    by the Developer: return `successful`
  - If the script failed for any other reason: return a detailed failure description including
    the exit code and the log file path so the orchestrator can find the output

**Never return script output directly.** All output is captured to the log file only.
