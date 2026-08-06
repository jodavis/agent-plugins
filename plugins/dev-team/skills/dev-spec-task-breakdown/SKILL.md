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

At the same time, rewrite every task's `**Depends on:**` line: replace each local task-number
reference (e.g. `Task 3`) with the real task-work-item key assigned to that task. Leave
`**Depends on:** — none —` lines unchanged.

Once every task's title and `Depends on:` line has been rewritten, validate the whole `## Tasks`
section by invoking `parse_task_dependencies` on the updated spec text — this is the first point
the dependency graph is guaranteed complete.

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
and reference (a dangling reference or a dependency cycle). Surface that error to the user and
fix the offending `Depends on:` line(s) before the spec is considered done — never leave a
dangling reference or cycle in the spec.

Once validation passes, for each task with one or more `Depends on:` entries, record the same
relationship in the tracker: use the matching adapter skill (per `get-project-configuration`'s
provider dispatch table) to link that task's tracked work item to each dependency's tracked work
item — e.g. for Jira, the `createIssueLink` operation from `work-with-Jira-tasks` (`Blocks` link
type, with the dependency as the blocker). Skip this for a provider whose adapter skill doesn't
document a linking operation, or when no tracker is configured.

Update the `## Related Features` table with the keys assigned to related feature-work-items.
