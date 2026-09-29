---
name: write-e2e-test
user-invocable: false
---

**Extension point skill** — projects must override this skill to specify their E2E test framework,
file locations, and conventions. Place a `SKILL.md` in `.claude/skills/write-e2e-test/` to define
these for this repo.

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
