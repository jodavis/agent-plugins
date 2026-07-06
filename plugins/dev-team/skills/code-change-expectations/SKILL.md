---
name: code-change-expectations
user-invocable: false
description: >
  Use when you are writing new code or fixing issues in existing code.
  Sets baseline expectations: build and test after each change, write unit tests first, and self-review before reporting.
---

Use this skill when:
- You are writing new code or fixing issues in existing code

## Expectations

### Always build and test the code you implement

After each change, build and test only the project(s) you modified:

```bash
dotnet build <project-path>
dotnet test <test-project-path> --filter "FullyQualifiedName~<ClassName>"
```

Where `<ClassName>` is the class you just modified or implemented. If the filter matches zero tests, run the full test project without `--filter`.

Do not run full validation scripts (`scripts/validate-build`, `scripts/validate-tests`, etc.) — those are run by the orchestrator after your step. Running them here is redundant.

### Always write unit tests first (TDD)

Use the `implement-task` skill's dispatcher when implementing new code. Write tests before writing implementation; confirm they fail before proceeding.

Use the `missing-test-harness` skill to determine which kinds of tests to write based on what already exists in the repo.

### Self-review before reporting

Before returning a work summary or fix summary, review the diff as if you were the reviewer:

- Does the change address what was asked?
- Are there missing test cases (branches, error paths, invalid inputs)?
- Where a component's logging differs by branch or condition, is that differentiation
  asserted — the same as any other observable behavior? (Not required when the member is
  branch-free.)
- Is there any scope creep — changes not required by the task?
- Do all files follow the code guidelines from `developer-standards`?
