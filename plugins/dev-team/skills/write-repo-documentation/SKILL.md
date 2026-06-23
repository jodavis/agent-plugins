---
name: write-repo-documentation
description: >
  Use when you are drafting or updating architecture documentation in this repo.
  Establishes where to put new documents, what they must contain, and the expected structure.
---

Use this skill when:
- You are drafting or updating architecture documentation in this repo

## File naming and location

Architecture documents are named `_doc_<FeatureName>.md` in PascalCase and live in the directory of the code they describe — not at the repo root.

Each `_spec_*.md` file includes a status note indicating it will become a `_doc_` file once implementation is complete:

```
> **Will become:** `_doc_<FeatureName>.md` once implementation is complete
```

When implementation is done, rename the spec file and update the status.

## Required content

Every `_doc_*.md` must start with a `Summary:` line — a single line description of what the document covers. This is used by tooling and other skills to discover relevant docs:

```
Summary: <one-line description of the subsystem or feature this doc covers>
```

After the summary, include:

- **Overview:** what this subsystem does and why it exists
- **Responsibilities & Boundaries:** what it owns, what it delegates, what it integrates with
- **Key Design Decisions:** decisions already made and their trade-offs — use the same ADR format as the spec
- **Key Classes / Interfaces:** the public surface — classes, interfaces, and their responsibilities
- **Data Flow:** how data moves through the subsystem

Omit sections that don't apply. Do not add sections that are not listed here without a clear reason.

## Updating an existing doc

When an implementation changes the design described in an existing `_doc_` file, update the doc as part of the same PR. A PR that changes a subsystem without updating its doc is incomplete.

If a new interface, responsibility, or dependency is added, reflect it in the doc. If a decision is reversed, update the Key Design Decisions section and note why.
