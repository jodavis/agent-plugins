---
name: design-work-items
user-invocable: false
description: >
  Use when you are writing a new design doc or a new part of an existing design doc.
  Updates the source work item (if any) with a summary after the design is finalized.
argument-hint: <work-item-id (optional)> <design-path>
---

**Extension point skill** — configure this via `get-project-configuration`'s `work-tracking`
section (preferred). Full-file override remains available as an escape hatch: place a `SKILL.md`
in `.claude/skills/design-work-items/` to replace this skill's process entirely.

Use this skill when:
- You are writing a new design doc or a new part of an existing design doc
- The design is finalized and its source work item (if any) should reflect the decisions

## Configured behavior

Invoke `get-project-configuration` and read `work-tracking`.

**If `work-tracking` is `null` or an empty map, this project has no issue tracker configured —
skip straight to Default behavior below.**

Otherwise, if the design's brief came from a tracked source work item (per `gather-brief-sources`'
output), dispatch to that provider's adapter skill per `get-project-configuration`'s provider
dispatch table to update the item's description:

- **Replace** (per `replace-description-when`): discard the existing description and write a
  concise summary — a brief overview of the problem and proposed solution, a bulleted list of the
  resulting deliverables with links to their feature-work-items, and a link to the design doc.
- **Update** (per `update-description-when`): merge the same content into the existing
  description rather than discarding it.

If the item's type doesn't match any configured item-type block, or neither condition clearly
applies, ask the user how to proceed rather than guessing.

If the design's brief had no tracked source work item (e.g. it originated from pasted notes or a
file), there is nothing to update — proceed to Default behavior's output line, substituting a note
that no source item was tracked.

## Default behavior (no project override, or `work-tracking` not configured, or no source item)

No work item integration is configured for this project, or no source work item exists for this
design. Do not create or update any work items.

Output: `No source work item to update; skipping work item updates.`
