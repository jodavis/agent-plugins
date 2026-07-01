---
name: write-repo-documentation
user-invocable: false
description: >
  Use when you are drafting or updating architecture documentation in this repo.
  Establishes where to put new documents, what they must contain, and the expected structure.
---

**Extension point skill** — projects must override this skill to define their documentation naming
convention, file locations, and required sections. Place a `SKILL.md` in
`.claude/skills/write-repo-documentation/` to define these for this repo.

Use this skill when:
- You are drafting or updating architecture documentation in this repo

## Default behavior (no project override)

Follow whatever documentation conventions already exist in this repo:

1. Search for existing documentation files and note their naming pattern, location, and structure.
2. Place new docs where other docs are found, e.g. next to the relevant code files or in a dedicated /docs folder. Follow the same naming pattern as existing docs.
3. Use the same section headings and structure as existing docs.

If no documentation exists yet, create a Markdown file next to the code it describes and include:
an overview of what the subsystem does, its key responsibilities, and its main integration points.

## Updating an existing doc

When an implementation changes a design described in an existing doc, update the doc as part of the
same PR. A PR that changes a subsystem without updating its doc is incomplete.
