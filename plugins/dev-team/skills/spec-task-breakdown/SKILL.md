---
name: spec-task-breakdown
user-invocable: false
description: >
  Use when breaking down a spec into tasks.
  Sizes tasks to roughly one PR each, creates Jira issues, and updates the spec with task links.
argument-hint: <path to _spec_*.md file> <epic-key (optional)>
---

Use this skill when:
- You are breaking down a spec into implementable tasks
- You need to create Jira issues for a set of spec tasks

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

If the spec has a `## Related Epics` section, add placeholder entries for those as well — titled `"Create epic: <name>"` with a one-line scope description. These become Jira epics, not tasks.

### 2 — Pause for approval

Save the updated spec and tell the user:

> Task breakdown written to `<path>`. Please review — edit any task or add `> **Review:** your comment`. Tell me when you're ready to create Jira issues.

**PAUSE — wait for approval or change requests. Apply any changes before continuing.**

### 3 — Determine the Jira epic

If the original input was a Jira epic key, use it directly.

Otherwise, use `AskUserQuestion` to ask: "Is there a Jira epic for this feature?" Provide options for "Yes — I'll provide the key", "No — create one now", "No — I'll create one later", and "No — skip Jira entirely".

**PAUSE — wait for the answer.**

If the user selects "Yes", collect the key. If "No — create one now", create it with `work-with-Jira-tasks` before proceeding.

### 4 — Create Jira issues

Use the `work-with-Jira-tasks` skill to create issues:

- **Tasks** → Jira Task type. Assign the epic as the parent if one is known.
- **"Create epic" placeholders** → Jira Epic type (no parent). Use the scope description as the epic summary.

### 5 — Update the spec

Replace each task title in `## Tasks` with a hyperlink to its Jira ticket. Keep all descriptions and exit criteria in place. The section remains in the spec permanently — future agents may not have Jira access.

Update the `## Related Epics` table with the Jira keys assigned to related epics.
