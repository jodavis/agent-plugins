---
name: write-repo-documentation
user-invocable: false
description: >
  Use when you are drafting or updating architecture documentation in this repo.
  Establishes where to put new documents, what they must contain, and the expected structure.
---

**Extension point skill** — configure this via `get-project-configuration`'s `documentation`
section (preferred). Full-file override remains available as an escape hatch: place a `SKILL.md`
in `.claude/skills/write-repo-documentation/` to replace this skill's process entirely.

Use this skill when:
- You are drafting or updating architecture documentation in this repo

## Configured behavior

Invoke `get-project-configuration` and read `documentation`.

- Place a post-implementation doc at `documentation.architecture.location` (relative to the repo
  root per the path-interpretation rule, unless it starts with `~`), named per
  `documentation.architecture.name-format` (e.g. `<slug>.md`).
- If drafting a pre-implementation PM-style design doc (via `design-first-draft`), place it at
  `documentation.specs.location` instead, named per `documentation.specs.name-format` (e.g.
  `<slug>_Design.md`).
- If drafting a pre-implementation dev spec (via `dev-spec-first-draft`), place it at
  `documentation.dev-specs.location` instead, named per `documentation.dev-specs.name-format`
  (e.g. `<slug>_Spec.md`).
- Write the doc in `documentation.format`.

### Standard doc structure

These conventions are not part of the YAML schema — they're process conventions applied
regardless of configuration (a future `documentation.required-sections` key is a reasonable
extension if a project needs to diverge from this list).

Every doc must start with a `Summary:` line — a single-line description of what the document
covers, used by tooling and other skills to discover relevant docs:

```
Summary: <one-line description of the subsystem or feature this doc covers>
```

After the summary, include whichever of these sections apply — do not add sections not listed
here:

- **Overview:** what this subsystem does and why it exists
- **Responsibilities & Boundaries:** what it owns, what it delegates, what it integrates with
- **Key Design Decisions:** decisions already made and their trade-offs
- **Key Classes / Interfaces:** the public surface — classes, interfaces, and their responsibilities
- **Data Flow:** how data moves through the subsystem

Do not go into implementation details — link to the source files for those.


## Updating an existing doc

When an implementation changes a design described in an existing architecture doc, update the doc as part of the
same PR. A PR that changes a subsystem without updating its doc is incomplete.
