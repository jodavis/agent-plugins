---
name: developer-standards
user-invocable: false
description: >
  Use when planning new code, writing code, or reviewing code.
  Loads project code guidelines and quality gates from CONTRIBUTING.md and CLAUDE.md.
---

**Extension point skill** — configure this via `get-project-configuration`'s
`developer-standards` section (preferred). Full-file override remains available as an escape
hatch: place a `SKILL.md` in `.claude/skills/developer-standards/` to replace this skill's
process entirely.

## Configured behavior

Invoke `get-project-configuration` and read `developer-standards` — a filename → description map,
each filename relative to the repo root. Follow each entry's own description to decide whether
it's expected to exist — see `get-project-configuration`'s `SKILL.md` for the convention that distinguishes soft (ignorable) entries from entries that are required.

Internalize all standards and apply to every file you plan, write, or review.

**If `developer-standards` is `null`** (a project has explicitly opted out of the shipped
default), no standards files are read.
