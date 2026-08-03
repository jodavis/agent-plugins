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
yet). Record whichever of `completed`/`failed: ...` it returns — this value is only a note to
carry forward into step 5's return; it is never itself a result to report, and **this is true for
`completed` exactly as much as for `failed: ...`.** Regardless of which one comes back, step 1 is
now finished and you must continue in the same turn to step 2, then 3, then 4, then 5 — a
`completed`/no-op hook result (e.g. the working tree was already clean, so there was nothing to
push) is not a stopping point and not an answer to return on its own. It means only that step 1
raised no objection; `<skill>` itself has not been invoked yet, so the task is not done.

This applies with **no less force** when step 1's `completed` came from the trivial case —
`before-<event>` is `null`/unconfigured in this project, so `run-event-hooks` made zero tool
calls and concluded immediately. That shape (a same-turn "nothing is configured, so this is a
no-op" observation with no intervening action) reads like a natural, final-sounding place to
stop, but it is the *most common* case across this pipeline's events, not a rare one — most
`before-<event>` keys are `null` by default, only a handful of events carry a real instruction.
Whether step 1's `completed` followed real work (a git check, a Jira call) or nothing at all
(the key was simply absent), the rule is identical: it is one note among several to fold into
step 5, and step 2 — actually invoking `<skill>` — still has not happened.

If `--event` was not given, skip this step entirely. Do not invoke `run-event-hooks` with an
empty event.

**Mechanical rule, not a judgment call:** the instant `run-event-hooks` returns — `completed` or
`failed: ...`, following real work or following nothing because the hook was `null` — your very
next tool call, in the same turn, is step 2's `Skill` invocation below. No sentence describes what
step 1 concluded; no summary comes first; nothing is written between the two tool calls. A
one-line "`before-<event>` is null, nothing to follow" observation, on its own, is never a valid
output of this skill at any point in the flow — noticing you are about to write one is exactly the
signal to make the step 2 tool call instead of writing it.

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

This is the *only* step that returns a result. Steps 1 and 4 each invoke `run-event-hooks` and get
back `completed`/`failed: ...`, but that is `run-event-hooks`' own internal return value to you,
the caller — not your answer to whoever invoked `workflow-worker`. Reaching step 1 or step 4's
`completed` is never a reason to stop and report; only step 5, after steps 2 and 3 have actually
happened, produces the status this skill hands back.

Return exactly one of:
- `successful` — if `<skill>` completed and its output was written to the context file, and (only
  when `--event` was given) both the before-event hook (step 1) and after-event hook (step 4)
  returned `completed`
- A detailed description of the failure — if `<skill>` itself failed to complete or write its
  output, **or** if either hook call from steps 1/4 returned `failed: ...` — fold that hook's
  failure summary into the description, even when `<skill>` itself succeeded

**Never return intermediate messages, skill output, or anything else.** All output goes to the context file only.
