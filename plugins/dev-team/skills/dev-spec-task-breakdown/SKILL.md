---
name: dev-spec-task-breakdown
user-invocable: false
description: >
  Use when breaking down a spec into tasks.
  Sizes tasks to roughly one PR each, creates tracked work items, and updates the spec with task links.
argument-hint: <path to _spec_*.md file> <feature-work-item-key (optional)>
---

Use this skill when:
- You are breaking down a spec into implementable tasks
- You need to create tracked work items for a set of spec tasks

## Sizing rules

Each task should be sized to roughly one PR — an appropriate amount of work for an agent to handle in one session. When in doubt, err on the side of smaller tasks.

Separate **human-required tasks** (configuration, infrastructure setup, access provisioning) from **agent tasks** (coding, writing documents). Label them clearly in the spec.

## Steps

### 1 — Draft the task breakdown

Add a `## Tasks` section at the end of the spec file. For each task write:

- A short title
- A one-sentence description
- Exit criteria as a checkbox list
- For tasks that include new E2E tests, write exit criteria as Gherkin-style acceptance scenarios (`Given / When / Then`)

If the spec has a `## Related Features` section, add placeholder entries for those as well —
titled `"Create feature-work-item: <name>"` with a one-line scope description. These become
feature-work-items, not task-work-items.

### 2 — Pause for approval

Save the updated spec and tell the user:

> Task breakdown written to `<path>`. Please review — edit any task or add `> **Review:** your comment`. Tell me when you're ready to create tracked work items.

**PAUSE — wait for approval or change requests. Apply any changes before continuing.**

### 3 — Determine the parent feature-work-item

Invoke `get-project-configuration` and read `work-tracking`. If it's `null` or empty, skip
straight to step 5 — no tracker is configured, so the spec's task list is the only record.

If the original input was a feature-work-item key, use it directly.

Otherwise, use `AskUserQuestion` to ask: "Is there a tracked feature-work-item for this
feature?" Provide options for "Yes — I'll provide the key", "No — create one now", "No — I'll
provide one later", and "No — skip work-item tracking entirely".

**PAUSE — wait for the answer.**

If the user selects "Yes", collect the key. If "No — create one now", create it with the
matching adapter skill (per `get-project-configuration`'s provider dispatch table) before
proceeding.

### 4 — Create tracked work items

Use the matching adapter skill (per `get-project-configuration`'s provider dispatch table) to
create issues:

- **Tasks** → the `task-work-item` type (`work-tracking.<provider>.task-work-item.type`, e.g.
  `Task` for a Jira project). Assign the feature-work-item as the parent if one is known.
- **"Create feature-work-item" placeholders** → the `feature-work-item` type
  (`work-tracking.<provider>.feature-work-item.type`, e.g. `Epic` for a Jira project; no
  parent). Use the scope description as the summary.

### 5 — Update the spec

Replace each task title in `## Tasks` with a hyperlink to its tracked work item, if one was
created. Keep all descriptions and exit criteria in place. The section remains in the spec
permanently — future agents may not have tracker access.

Update the `## Related Features` table with the keys assigned to related feature-work-items.
