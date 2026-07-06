---
name: tdd-practices
user-invocable: false
description: >
  Reference skill for TDD practice rules — AAA structure, red-must-fail-for-the-right-reason,
  frozen-Arrange/Act, and the default test naming convention. Non-negotiable dev-team process
  conventions, language/stack-agnostic except the naming rule's syntax.
---

Use this skill when:
- You are writing or reviewing unit tests as part of the TDD ping-pong protocol, or any other
  test-first workflow that follows these conventions

## Practice rules

These rules are process/behavioral conventions, not tied to any particular language or stack —
only the naming rule's syntax defers to the target project.

### AAA structure

Every test is Arrange, Act, Assert, in that order: set up state and dependencies (Arrange),
invoke the behavior under test (Act), then verify the outcome (Assert).

### Red must fail for the right reason

A test's failure must always be a genuine behavioral mismatch — never a compile error, typo,
or broken setup in disguise. Confirming a test fails is not enough on its own; confirm it
fails for the reason you expect (missing or incorrect behavior), not for an unrelated reason.

### Arrange and Act are frozen after first green

Once a test's first Assert has gone green, that test's Arrange and Act are frozen: only
additional `Assert` statements may be appended afterward, for closely related follow-on
behaviors of the same scenario. A genuinely different scenario is always a new test method —
never a rewritten Arrange or Act on an existing one.

### Naming convention

Default to `<Component>_<Scenario>_<ExpectedResult>` for test names. Use the
`developer-standards` skill to check whether the target project documents its own test naming
convention; when it does, that convention takes precedence over this default.
