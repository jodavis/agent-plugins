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
instructions and complete all its steps.

`<skill>`'s own final step writes its deliverable to a scratch file — via the
`write-scratch-deliverable` skill — instead of returning it as chat text; `dev_team.py`'s
`merge_pending_deliverables()` picks that file up and merges it into `<context-file>`'s
`<write-section>` section on the next orchestration-loop iteration. `<context-file>` and
`<write-section>` (this skill's own arguments, above) are exactly what `write-scratch-deliverable`
needs to compute that scratch file's path — they stay in scope for `<skill>`'s own steps since
`<skill>` runs inside this same session, not a separate one, so there is nothing further for you
to pass along explicitly.

**Do not** write to `<context-file>` yourself, with `Edit` or otherwise — `<skill>`'s own final
step already did (via the scratch file), and a direct `Edit` here would race with the
deterministic merge step over the same content.

### 2 — Return status

This is the *only* step that returns a result. Return exactly `<skill>`'s own final chat output,
verbatim:
- `successful` — if `<skill>` completed and wrote its deliverable to the scratch file
- A detailed description of the failure — if `<skill>` itself failed to complete

**Never return intermediate messages, skill deliverable content, or your own summary of what
`<skill>` did.** The deliverable itself already went to the scratch file in step 1, not through
you.
