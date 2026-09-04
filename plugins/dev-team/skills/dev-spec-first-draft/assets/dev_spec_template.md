# \<Feature Name\>

> **Status:** Draft
> **Design:** `_design_<FeatureName>.md` — the detailed design doc this spec implements, if one
> exists; otherwise "— none"
> **Architecture doc:** `_doc_<FeatureName>.md` — authored by `dev-spec-task-breakdown`'s
> unconditional final "Author design documentation" task once implementation completes; this
> spec persists afterward for harvesting

This line names an obligation owned by `dev-spec-task-breakdown`, not by this skill: every task
breakdown must append that unconditional final documentation task, so the reference above is
always honored. If `dev-spec-task-breakdown` does not yet append it, treat that as a gap in
`dev-spec-task-breakdown`, not a reason to omit the header line here.

## Contents

_(Write or regenerate this section last, after every other section is in place, so it reflects
the final heading set rather than a stale mid-draft one.)_

- [Overview](#overview)
- [Responsibilities & Boundaries](#responsibilities--boundaries)
- [Key Design Decisions](#key-design-decisions)
- [Component Breakdown](#component-breakdown)
- [Planned Implementation](#planned-implementation)
- [Related Features](#related-features)
- [Open Questions](#open-questions)
- [Related Docs](#related-docs)

## Overview

One paragraph: what this feature does and why it exists.

## Responsibilities & Boundaries

- **Owns:** ...
- **Does not own:** ...
- **Integrates with:** ...

## Key Design Decisions

### \<Decision title\>

_Context:_ Why this choice was needed.
_Decision:_ What was decided.
_Consequences:_ Trade-offs accepted.

_(Repeat for each significant decision.)_

## Component Breakdown

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `<Name>` | Wrapper \| Testable \| Orchestrator | One sentence | `<Component>`, `<Component>`, or — |

Use the `component-taxonomy` skill for the Wrapper/Testable/Orchestrator definitions and the
property-level Wrapper carve-out to classify every planned component.

When identifying Testable components, apply these isolation patterns as authoring guidance:

- Prefer dependency injection to isolate a component from its collaborators.
- Consider the **State Object** pattern for stateful components: state lives as plain,
  directly-observable fields on a data object. By default, only the owning/controller
  service mutates it; other services may read it. Some components legitimately invert
  this — a ViewModel-style State Object is written directly by its consumer (e.g. the UI),
  and the owning controller subscribes to change notifications on it to react. In this
  inverted case, both sides may read and write the object; design each field's ownership
  deliberately rather than assuming a single default direction.
- Prefer synchronous logic for anything complex; gather async data up front and pass the
  results in, rather than doing async work on demand inside complex logic.
- Where practical, build each component before its dependencies exist, using mocks of the
  interfaces, so the dependency interfaces reflect real usage rather than speculative design.

## Planned Implementation

### Interfaces

Public interfaces — method signatures, types, and responsibilities.

### Key Classes

Planned classes, their roles, and important relationships.

### Data Flow

How data moves through the feature from trigger to output.

## Related Features

Features identified during drafting that are out of scope here and will be spec'd separately.

| Feature | Scope |
|------|-------|
| (this feature) | ... |

_(Omit if there are no related features.)_

## Open Questions

_(Reserved for items the user explicitly deferred — see step 1. An empty section is the normal,
expected outcome.)_

- [ ] Unresolved question

## Related Docs

Links to the documentation files consulted during drafting.
