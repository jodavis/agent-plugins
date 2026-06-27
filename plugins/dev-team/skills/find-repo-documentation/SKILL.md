---
name: find-repo-documentation
description: >
  Use when you need to learn the architecture from documentation in this repo.
  Discovers available architecture docs and reads the ones relevant to the current task.
argument-hint: <task context or area to research>
---

**Extension point skill** — projects should override this skill to describe where their architecture
docs live and how to discover them. Place a `SKILL.md` in `.claude/skills/find-repo-documentation/`
to define the doc naming convention and discovery mechanism for this repo.

Use this skill when:
- You need to learn the architecture from documentation in this repo

## Default behavior (no project override)

Search for architecture documentation using common patterns:

1. Check for a `docs/` or `doc/` directory and list its contents.
2. Look for Markdown files in the repo root (excluding `README.md`).
3. Read `README.md` if it exists.

From these, select and read the files most relevant to the current task. For each doc consulted,
note its file path and any constraints, patterns, or conventions that apply to the work ahead.
