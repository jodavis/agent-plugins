---
name: dev-spec-create-work-items
user-invocable: false
description: >
  Use when an approved, readiness-reviewed task breakdown needs tracked work items.
  Creates task-work-items and feature-work-items, links task dependencies, and updates the spec with the assigned keys.
argument-hint: <path to _spec_*.md file> <feature-work-item-key (optional)>
---

Use this skill when:
- A spec's task breakdown has been drafted, approved, and readiness-reviewed
- You need to create tracked work items for a set of spec tasks

## Steps

### 1 — Determine the parent feature-work-item

Invoke `get-project-configuration` and read `work-tracking`. If it's `null` or empty, skip
straight to step 3 — no tracker is configured, so the spec's task list is the only record.

If the original input was a feature-work-item key, use it directly.

Otherwise, use `AskUserQuestion` to ask: "Is there a tracked feature-work-item for this
feature?" Provide options for "Yes — I'll provide the key", "No — create one now", "No — I'll
provide one later", and "No — skip work-item tracking entirely".

**PAUSE — wait for the answer.**

If the user selects "Yes", collect the key. If "No — create one now", create it with the
matching adapter skill (per `get-project-configuration`'s provider dispatch table) before
proceeding.

### 2 — Create tracked work items

Use the matching adapter skill (per `get-project-configuration`'s provider dispatch table) to
create issues:

- **Tasks** → the `task-work-item` type (`work-tracking.<provider>.task-work-item.type`, e.g.
  `Task` for a Jira project). Assign the feature-work-item as the parent if one is known.
- **"Create feature-work-item" placeholders** → the `feature-work-item` type
  (`work-tracking.<provider>.feature-work-item.type`, e.g. `Epic` for a Jira project; no
  parent). Use the scope description as the summary.

### 3 — Update the spec

Replace each task title in `## Tasks` with a hyperlink to its tracked work item, if one was
created — preserving the trailing 🧑/🤖 marker already on that heading (from
`dev-spec-task-breakdown` step 1, or a human edit made during that skill's step 2 pause)
immediately after the new hyperlink, never dropped or reintroduced from scratch. Keep all
descriptions and exit criteria in place. The section remains in the spec permanently — future
agents may not have tracker access.

At the same time, rewrite every task's `**Depends on:**` line: replace each local task-number
reference (e.g. `Task 3`) with the real task-work-item key assigned to that task. Leave
`**Depends on:** — none —` lines unchanged.

Once every task's title and `Depends on:` line has been rewritten, validate the whole `## Tasks`
section by invoking `parse_task_dependencies` on the updated spec text — this is the first point
the dependency graph is guaranteed complete. This same invocation also validates every heading's
trailing 🧑/🤖 marker (`validate_task_headings`, run automatically before the graph is parsed),
so a marker dropped or malformed during the rewrite above is caught right here too.

`<skill-dir>` below refers to this skill's own base directory — the "Base directory for this
skill" path shown when this skill was invoked. Resolve it to that literal path; it is not an
environment variable. `task_dependencies.py` lives in the sibling `workflow-orchestrate` skill's
`scripts/` directory, reachable relative to `<skill-dir>` — this skill may run in a repo other
than the one containing these plugin files (e.g. as an installed plugin), so resolve the path
this way rather than assuming a particular repo layout or that the Bash tool's CWD is the repo
root. Run it via `Bash`:

```bash
python3 "<skill-dir>/../workflow-orchestrate/scripts/task_dependencies.py" "<path to spec file>"
```

If it exits non-zero, it printed a clear `Error: ...` message to stderr naming the offending task
and reference (a dangling reference, a dependency cycle, or a heading missing/malformed on its
trailing 🧑/🤖 marker). Surface that error to the user and fix the offending line before the spec
is considered done — never leave a dangling reference, cycle, or missing/malformed marker in the
spec.

Once validation passes, for each task with one or more `Depends on:` entries, record the same
relationship in the tracker: use the matching adapter skill (per `get-project-configuration`'s
provider dispatch table) to link that task's tracked work item to each dependency's tracked work
item — e.g. for Jira, the `createIssueLink` operation from `work-with-Jira-tasks` (`Blocks` link
type, with the dependency as the blocker). Skip this for a provider whose adapter skill doesn't
document a linking operation, or when no tracker is configured.

Update the `## Related Features` table with the keys assigned to related feature-work-items.
