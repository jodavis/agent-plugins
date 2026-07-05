---
name: test-driven-development
user-invocable: false
description: >
  Use when you are writing new code or fixing issues in existing code.
  Implements using TDD: E2E tests first, then unit tests and implementation one component at a time.
argument-hint: <task context or exit criteria>
---

Use this skill when:
- You are writing new code or fixing issues in existing code

## Steps

### 1 — Write E2E / API tests first

Write Gherkin scenarios that cover the exit criteria before writing any implementation code. Use existing steps whenever possible. When new steps are needed:
- Use generalized `When` / `Then` / `Given` phrasing — each step should be something a human could do or observe manually
- Step definitions delegate logic to test service methods

Run the new scenarios and confirm they fail. A failure here means "not implemented yet" — if they fail for a build or infrastructure reason instead, fix that first.

### 2 — Implement one component at a time

For each component:

**a. Write unit tests**

Write unit tests before implementing the component. Confirm the tests fail before proceeding — but for the right reason (missing implementation), not for build break reasons.

**b. Implement**

Implement the component until the unit tests pass.

**c. Build and test**

After each component, verify only the code you modified:

```bash
dotnet build <project-path>
dotnet test <test-project-path> --filter "FullyQualifiedName~<ClassName>"
```

Where `<ClassName>` is the class you just implemented. If the filter matches zero tests, run the full test project without `--filter`.

Fix any build errors or new test failures before moving to the next component.

### 3 — Confirm E2E tests pass

Once all components are implemented, run the full E2E scenario suite and confirm all new scenarios pass.

## Practice rules

These rules apply to every test written under this skill. They are process/behavioral
conventions, not tied to any particular language or stack — only the naming rule's syntax
defers to the target project.

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
