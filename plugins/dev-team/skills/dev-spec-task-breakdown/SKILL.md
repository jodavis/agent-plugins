---
name: dev-spec-task-breakdown
user-invocable: false
description: >
  Use when breaking down a spec into tasks.
  Sizes tasks to roughly one PR each and drafts the spec's Tasks section for user approval.
argument-hint: <path to _spec_*.md file>
---

Use this skill when:
- You are breaking down a spec into implementable tasks
- You need to draft a task breakdown for user approval before tracked work items are created

## Sizing rules

Each task should be sized to roughly one PR — an appropriate amount of work for an agent to handle in one session. When in doubt, err on the side of smaller tasks.

Separate **human-required tasks** (configuration, infrastructure setup, access provisioning) from **agent tasks** (coding, writing documents). Label them clearly in the spec.

## Steps

### 1 — Draft the task breakdown

Add a `## Tasks` section at the end of the spec file. For each task write:

- A short title
- A `**Depends on:** <ref>[, <ref>...]` line directly under the title, naming the other tasks in
  this breakdown it depends on — or `**Depends on:** — none —` when it has none. `<ref>` is the
  task's local number (e.g. `Task 3`, matching this same section's `### Task N: ...` heading
  convention) since real task-work-item keys don't exist yet at this point. Infer dependencies
  best-effort from the design, the same way titles and descriptions already are — a task whose
  description says it builds on another task's interfaces gets that task named as a dependency.
  A task may depend on more than one other task, comma-separated.
- **Hard rule: write every task after all of its own `Depends on:` entries.** The `## Tasks`
  section's document order *is* the stack order — nothing computed or persisted from it later —
  so a task must never appear before a task it depends on. This is not the same as the softer,
  non-enforced guideline (elsewhere) to order human-operator tasks as late as possible; this rule
  is mandatory for every task, human or agent.
- A one-sentence description
- Exit criteria as a checkbox list
- For tasks that include new E2E tests, write exit criteria as Gherkin-style acceptance scenarios (`Given / When / Then`)

If the spec has a `## Related Features` section, add placeholder entries for those as well —
titled `"Create feature-work-item: <name>"` with a one-line scope description. These become
feature-work-items, not task-work-items.

### 2 — Pause for approval

Save the updated spec and tell the user:

> Task breakdown written to `<path>`. Please review — edit any task or add `> **Review:** your comment`. Tell me when you're ready to continue.

**PAUSE — wait for approval or change requests. Apply any changes before continuing.**
