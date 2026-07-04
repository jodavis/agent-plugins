---
name: write-task-brief
user-invocable: false
description: >
  Use when you are writing a task brief for a work item.
  Produces a structured implementation plan from a spec section and research findings.
argument-hint: <task-key> <spec-section> <research-findings>
---

Use this skill when:
- You have completed research for a work item and need to write the task brief

## Task brief format

Open with this exact heading (substitute the real task key):

```
# Implementation plan for <task-key>
```

The brief must include all of the following sections (**Components in scope** is
conditional — see below):

**Task title and description**
One sentence stating what the task accomplishes and why.

**Exit criteria**
Copy the exit criteria checklist from the spec section verbatim. If the spec uses Gherkin scenarios, include them.

**Key design decisions**
Decisions already made in the spec that directly constrain this task's implementation. Do not include decisions from other parts of the spec that don't affect this task.

**Components in scope**
Only relevant when the spec has a `## Component Breakdown` section (see `spec-first-draft`
for the table format: `| Component | Type | Responsibility | Depends on |`). That table lives
once, spec-wide — not inside this task's own spec-section excerpt — so look it up separately:
use the `use-context-file` skill with the task key to read `spec_path` from the context file,
then read that spec file and locate its `## Component Breakdown` table.

- **No Component Breakdown section anywhere in the spec:** omit "Components in scope"
  entirely from the brief — do not write an empty heading.
- **Component Breakdown section exists:** determine which rows belong to this task by
  matching component names against the task's title, description, exit criteria, and any
  files/areas it names. Component names are logical names, not file paths — match by
  judgment, the same way the task's own prose already identifies the files/areas it affects.
  - **Zero matching rows** (e.g. a scaffolding/setup task with no classified-component work):
    write the heading with an explicit empty list — do not omit the section. This is the
    signal that this task has no components to implement one at a time; it is implemented
    directly instead of via per-component TDD.
  - **One or more matching rows:** filter the table to just those rows, then list them as a
    flat, topologically-sorted list — a component always appears after every other in-scope
    component it depends on. For each component's `depends on` entries, include only
    dependencies that are themselves in the filtered subset; a dependency on a component
    outside this task's scope (e.g. built by an earlier task) is already committed elsewhere,
    so omit it from the printed edge — the component still keeps its correct position
    relative to its in-scope dependencies. If the filtered subset's dependency edges form a
    cycle (no valid topological order exists), list the components in their original table
    order instead and add a note under Known ambiguities identifying the cycle.

Format when populated (matches the illustrative example in `_spec_TddForImplementation.md`):
```
## Components in scope

1. `TokenCache` — Testable — depends on: —
2. `AuthOrchestrator` — Orchestrator — depends on: `TokenCache`
```

Format when explicitly empty:
```
## Components in scope

(none — this task touches no classified components)
```

**Files and interfaces to create or modify**
List each file by path. For each: whether it is new or modified, and one sentence on what changes. Call out existing utilities, base classes, or patterns the developer should reuse rather than reinvent — include file paths.

**Known ambiguities**
Concrete questions the developer may need answered before or during implementation. Only include genuine gaps — not rhetorical questions or things already resolved in the spec.
