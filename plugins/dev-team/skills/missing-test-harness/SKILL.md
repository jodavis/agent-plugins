---
name: missing-test-harness
user-invocable: false
description: >
  Use when you are planning or writing unit, E2E, or API tests.
  Establishes which test harnesses exist in the repo and prevents creating new ones without explicit instruction.
---

Use this skill when:
- You are planning or writing unit, E2E, or API tests

## Rules

Use the existing test harnesses in the repo. If a test harness does not exist for a given type of code, do not create one unless explicitly instructed to do so.

**Examples:**

- A repo has unit tests in C# and Python, and E2E tests only for C# code. When writing Python code, do not invent an E2E test strategy for Python — only write unit tests.
- When writing documentation, do not write any tests unless there is already a documentation testing setup in the repo.
- When adding a new file type that has no test coverage pattern, ask before establishing a new pattern.

## How to determine what exists

Scan the repo for existing test projects and test files:

```bash
find . -name "*Test*" -o -name "*Spec*" -o -name "*.feature" | grep -v ".git" | sort
```

Look for:
- Unit test projects and their language/framework
- E2E test feature files and their runner setup
- API test collections or scripts

Only write tests that fit the patterns already established. If a harness is absent for the area you are testing, note the gap in your report and do not invent a solution.
