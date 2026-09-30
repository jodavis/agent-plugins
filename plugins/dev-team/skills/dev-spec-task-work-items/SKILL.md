---
name: dev-spec-task-work-items
user-invocable: false
---

**Extension point skill** — configure this via `get-project-configuration`'s `work-tracking`
section (preferred). Full-file override remains available as an escape hatch: place a `SKILL.md`
in `.claude/skills/dev-spec-task-work-items/` to replace this skill's process entirely.

## Configured behavior

Invoke `get-project-configuration` and read `work-tracking`.

**If `work-tracking` is `null` or an empty map, this project has no issue tracker configured —
skip straight to Default behavior below.**

Otherwise, for the relevant provider (matched via `identify-project-work-items`), dispatch to its
adapter skill per `get-project-configuration`'s provider dispatch table to update each affected
work item's description. For each item, look up its item-type block (e.g.
`task-work-item`, `feature-work-item`) by matching the item's type against the block's `type`
field, and use whichever of `replace-description-when` / `update-description-when` best matches
the current situation to decide whether to replace the description outright or merge into the
existing one:

- **Replace** (per `replace-description-when`): discard the existing description and write a
  concise summary — for a feature-work-item, a brief overview and a bulleted list of key
  decisions and outcomes with a link to the spec file; for a task-work-item, a one-paragraph
  overview of what the task implements, a bulleted list of relevant decisions, and a reference to
  the spec section (`See spec: <relative path>`).
- **Update** (per `update-description-when`): merge the same content into the existing
  description rather than discarding it.

If an item's type doesn't match any configured item-type block, or neither condition clearly
applies, ask the user how to proceed rather than guessing.

## Default behavior (no project override, or `work-tracking` not configured)

No work item integration is configured for this project. Do not create or update any work items.

Output: `No work item integration configured; skipping work item updates.`
