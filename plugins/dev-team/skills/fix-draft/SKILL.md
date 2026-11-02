---
name: fix-draft
user-invocable: false
---

You are reading from the workflow context file, fixing issues in existing code, and committing changes locally to the repo.

## Steps

### 1 — Identify the work item

Use the `identify-project-work-items` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the original task brief and work summary from the context file, and ensure the working branch is set up.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates.

Do not run full validation scripts after making changes — that is the responsibility of another pipeline step. Build and test only the code you modified.

### 4 — Triage and fix each issue

Address issues one at a time. For each issue:

**Triage:**

- **Build error:** locate the root cause in the source or test files. Do not patch over symptoms.
- **Test failure:** confirm whether the test itself is correct before touching production code. If the test is wrong, fix the test and explain why in the report. If the test is right, write a failing unit test that isolates the defect, then fix the code.

**Fix:**

After each fix, build and run just the tests for the project(s) you changed, using this
project's own build/test tooling — e.g. for .NET:

```bash
dotnet build <project-path>
dotnet test <test-project-path> --filter "FullyQualifiedName~<ClassName>"
```

for Python: `pytest <path-to-test-file-or-class>`; for JS/TS: `npm test -- <pattern>`. If a
narrower filter/pattern matches zero tests, fall back to running the whole test project/module
rather than skipping verification.

**Commit each fix separately** using the `commit-changes` skill with a message describing the specific issue resolved. One commit per issue — do not batch multiple fixes into a single commit.

### 5 — Self-review

Review the diff for unintended scope, missed issues, and convention violations.

### 6 — Report

Compose a fix summary as structured prose: for each issue, one sentence describing what was
changed and why. Use the `write-scratch-deliverable` skill to write it in place of returning it
as chat text.
