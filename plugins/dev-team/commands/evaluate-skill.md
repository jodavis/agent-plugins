---
description: >
  Evaluate a skill directory (its SKILL.md and supporting files) against best practices —
  structure, terseness, gotchas, scripting of fragile logic, and whether its description
  actually triggers as intended. Reports findings, not a pass/fail gate.
argument-hint: <path-to-skill-directory>
---

Use the `skill-checklist-review` skill to evaluate the skill directory given as `$1` (resolve it
relative to the repo root if given as a bare name, e.g. `review` → `plugins/dev-team/skills/review`).

If no argument was given, ask which skill directory to evaluate.

If the report has any actionable finding (any Group A finding, or a Group B item that doesn't
hold), use `AskUserQuestion`: "Draft proposed fixes for these findings now?" If yes, invoke the
`skill-fix-proposal` skill against the same target directory. If no, stop — the report stands on
its own.
