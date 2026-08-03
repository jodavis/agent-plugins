---
name: workflow-script
user-invocable: false
description: >
  **Runs a Python script as part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run a script step in an orchestrated workflow.
argument-hint: --context-file <path> --write-section <section> --command <command> --log-file <log_file> [--event <name>]
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write the log file path to (e.g. `Build Result`)
- `--command` — the shell command to run (e.g. `python3 -u /path/to/validate.py PROJ-123`),
  already fully resolved by the caller (sometimes literally `python3 ...`, sometimes built by
  `dev_team.py` using `sys.executable`). This is a documented carve-out from the `run-python-script`
  skill: `--command` is a pre-built shell string handed in by the caller, not a `python3 <script>`
  invocation this skill constructs itself, so step 2 below keeps running it directly via `Bash`
  rather than delegating to `run-python-script` — see `run-python-script/SKILL.md`'s
  "Carve-outs" section.
- `--log-file` — a full path to a location where the script's output should be logged
- `--event` — (optional) the pipeline event name for this step (e.g. `validate`), matching a
  `dev_team.py` `Step`'s `EVENT_NAME`. When present, wraps the command run with the project's
  configured before-/after-event instructions via `run-event-hooks`. When absent, no hook calls
  are made at all — behavior is identical to before this argument existed.

## Steps

### 1 — Run the before-event hook (only when `--event` is present)

If `--event` was given, invoke the `run-event-hooks` skill with
`--event <event> --phase before --context-file <context-file>` (no `--outcome` — nothing has run
yet). Record whichever of `completed`/`failed: ...` it returns; do not let a `failed` result stop
you from proceeding to step 2 — carry it forward to fold into step 6's return.

If `--event` was not given, skip this step entirely. Do not invoke `run-event-hooks` with an
empty event.

### 2 — Run the command

Run the command via Bash, capturing combined stdout and stderr to the log file:

```bash
<command> > "<log_file>" 2>&1
```

### 3 — Determine the result

1. Read the last non-empty line of the log file.
2. If that line is a valid JSON object (starts with `{` and ends with `}`), use it verbatim as
   `<result>` — regardless of exit code. This lets scripts communicate structured status.
3. Otherwise: use `Succeeded` if the exit code is 0, or a short failure description (including
   the exit code) if non-zero.

Compute this before step 4 so `<result>` is available both for writing the context-file section
and for step 5's after-hook `<outcome>`.

### 4 — Write the log path to the context file

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

**If the sentinel `<!-- section:<write-section> -->` already exists:** use `Edit` to replace all
content between the sentinel and the next `<!-- section:` marker or end of file.

**If the sentinel does not exist:** use `Edit` to append the sentinel and content after the last
line of the file.

### 5 — Run the after-event hook (only when `--event` is present)

If `--event` was given, compute `<outcome>` from the **validation result itself** — `success` if
`<result>` (from step 3) starts with `Succeeded`, `failure` otherwise. This is a separate
judgment from step 6's own return contract: mirrors `ValidateStep.handle_results()`'s own
`result.startswith("Succeeded")` check in `dev_team.py`, not the command's exit code and not step
6's "a failing build/test run is still a successful script run" rule. Invoke the
`run-event-hooks` skill with `--event <event> --phase after --outcome <outcome>
--context-file <context-file>`. Record whichever of `completed`/`failed: ...` it returns.

If `--event` was not given, skip this step entirely.

### 6 — Return status

Determine the script's own base result exactly as before this feature existed:

- If the exit code is zero: the base result is `successful`
- If the exit code is non-zero:
  - If the script failed because of build or test failures, that is expected and will be fixed
    by the Developer: the base result is `successful`
  - If the script failed for any other reason: the base result is a detailed failure description
    including the exit code and the log file path so the orchestrator can find the output

Then fold in the hook results: if either `run-event-hooks` call from steps 1/5 returned
`failed: ...`, the overall return is a detailed failure description (including that hook's
failure summary) **regardless of the base result above** — even when the base result was
`successful`. Otherwise, return the base result unchanged.

**Never return script output directly.** All output is captured to the log file only.
