---
name: find-repo-documentation
user-invocable: false
description: >
  Use when you need to learn the architecture from documentation in this repo.
  Discovers available architecture docs and reads the ones relevant to the current task.
argument-hint: <task context or area to research>
---

**Extension point skill** — configure this via `get-project-configuration`'s `documentation`
section (preferred). Full-file override remains available as an escape hatch: place a `SKILL.md`
in `.claude/skills/find-repo-documentation/` to replace this skill's process entirely.

Use this skill when:
- You need to learn the architecture from documentation in this repo

## Configured behavior

Invoke `get-project-configuration` and read `documentation`. Run
`documentation.architecture.search` as a shell command to discover candidate docs
(`documentation.architecture.location`, if referenced, is relative to the repo root per the
path-interpretation rule in `get-project-configuration`'s `SKILL.md`, unless it starts with `~`).

From the discovered files, select and read the ones most relevant to the current task. For each
doc consulted, note its file path and any constraints, patterns, or conventions that apply to the
work ahead.
