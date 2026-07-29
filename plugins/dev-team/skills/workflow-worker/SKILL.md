---
name: workflow-worker
user-invocable: false
description: >
  **Defines the rules for working as a part of a multi-agent orchestrated workflow.**
  Use this skill when an agent is instructed to run as an orchestrated worker.
argument-hint: --context-file <path> --write-section <section> --skill <skill> [--skill-args <args>] [--event <name>]
---

## Arguments

- `--context-file` — absolute path to the workflow context file (e.g. `~/.dev-team/org/repo/PROJ-123.md`)
- `--write-section` — name of the section to write output to (e.g. `Researcher Brief`)
- `--skill` — name of the skill to invoke
- `--skill-args` — (optional) arguments to pass to the skill
- `--event` — (optional) the pipeline event name for this step (e.g. `implement`, `signoff`),
  matching a `dev_team.py` `Step`'s `EVENT_NAME`. When present, wraps the skill invocation with
  the project's configured before-/after-event instructions via `run-event-hooks`. When absent,
  no hook calls are made at all — behavior is identical to before this argument existed.

`<skill-dir>` below refers to this skill's own base directory — the "Base directory
for this skill" path shown when this skill was invoked. Resolve it to that literal
path; it is not an environment variable.

## Steps

### 1 — Run the before-event hook (only when `--event` is present)

If `--event` was given, invoke the `run-event-hooks` skill with
`--event <event> --phase before --context-file <context-file>` (no `--outcome` — nothing has run
yet). Record whichever of `completed`/`failed: ...` it returns; do not let a `failed` result stop
you from proceeding to step 2 — carry it forward to fold into step 5's return.

If `--event` was not given, skip this step entirely. Do not invoke `run-event-hooks` with an
empty event.

### 2 — Invoke the skill

Use the `Skill` tool to invoke `<skill>` with `<skill-args>` as arguments. Follow the skill's
instructions and complete all its steps. Capture the output — do not return it to the caller
yet.

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

### 4 — Run the after-event hook (only when `--event` is present)

If `--event` was given, determine `<outcome>` from the same judgment step 5 already makes about
`<skill>` itself: `success` if `<skill>` completed all its steps and its output was written in
step 3, `failure` otherwise. Invoke the `run-event-hooks` skill with
`--event <event> --phase after --outcome <outcome> --context-file <context-file>`. Record
whichever of `completed`/`failed: ...` it returns.

If `--event` was not given, skip this step entirely.

### 5 — Return status

Return exactly one of:
- `successful` — if `<skill>` completed and its output was written to the context file, and (only
  when `--event` was given) both the before-event hook (step 1) and after-event hook (step 4)
  returned `completed`
- A detailed description of the failure — if `<skill>` itself failed to complete or write its
  output, **or** if either hook call from steps 1/4 returned `failed: ...` — fold that hook's
  failure summary into the description, even when `<skill>` itself succeeded

**Never return intermediate messages, skill output, or anything else.** All output goes to the context file only.
