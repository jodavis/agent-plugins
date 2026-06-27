---
name: write-e2e-test
description: >
  Use when you are writing E2E tests.
  Establishes where to put feature files, how to write test scenarios, and how they should be structured.
---

**Extension point skill** — projects must override this skill to specify their E2E test framework,
file locations, and conventions. Place a `SKILL.md` in `.claude/skills/write-e2e-test/` to define
these for this repo.

Use this skill when:
- You are writing E2E tests

## Default behavior (no project override)

Examine the project's existing test structure to determine conventions:

1. Find the E2E or integration test directory:
   ```bash
   find . -type d \( -name "*e2e*" -o -name "*EndToEnd*" -o -name "*integration*" \) | head -10
   ```
2. Read a sample of existing test files to understand the scenario format and file structure.
3. Place the new test file in the same directory as other E2E tests, following the same naming
   pattern.
4. Follow the same scenario format and step structure as existing tests.
