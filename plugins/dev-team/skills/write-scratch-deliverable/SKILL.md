---
name: write-scratch-deliverable
user-invocable: false
---

## Steps

### 1 — Compute the scratch file path

- `<pending-dir>` = `<context-file>`'s parent directory, plus `.pending/`. Create it first if it
  doesn't already exist — `mkdir -p "<pending-dir>"` via `Bash`. Do not assume `Write` creates
  missing parent directories itself.
- `<section-slug>` = `<write-section>` with every space replaced by `_` (e.g. `Post-Handoff Fix 3`
  → `Post-Handoff_Fix_3`). No section name this pipeline uses contains a literal underscore, so
  this substitution is unambiguous for `dev_team.py`'s `merge_pending_deliverables()` to reverse.
- The scratch file path is `<pending-dir>/<work-item-id>__<section-slug>.md`.

### 2 — Write the deliverable

Use the `Write` tool to write your complete, already-composed deliverable — exactly the content
you would otherwise have returned as your final chat message, including any trailing status
marker your own skill's instructions specify (e.g. a JSON status line) — as the entire content of
that scratch file. Compose the content directly as this `Write` call's own content; never produce
it as chat text first and write it in a later action — composing the deliverable and persisting it
must be the same action, with nothing left to remember afterward.

If a scratch file already exists at that exact path (a rare re-run of the same step), overwrite it
— `merge_pending_deliverables()` only ever reads the latest content before deleting it.

### 3 — Return

Return exactly one word: `successful`. This applies only when your own skill's work genuinely
completed; if it did not (a real failure, not merely "nothing changed"), skip step 2 and instead
return a detailed description of the failure, the same as you would have without this skill.
