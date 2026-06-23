---
name: fix-draft
description: >
  Use when fixing build failures or test failures for a work item that does not yet have a GitHub PR.
  Reads the task brief, triages each issue, commits fixes one at a time, and returns a fix summary.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are fixing build failures or test failures
- There is no existing GitHub PR for the work item yet

You are reading from the workflow context file, fixing issues in existing code, and committing changes locally to the repo.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

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

After each fix, build and test only the project(s) you changed:

```bash
dotnet build <project-path>
dotnet test <test-project-path> --filter "FullyQualifiedName~<ClassName>"
```

If the filter matches zero tests, run the full test project without `--filter`.

**Commit each fix separately** using the `commit-changes` skill with a message describing the specific issue resolved. One commit per issue — do not batch multiple fixes into a single commit.

### 5 — Self-review

Review the diff for unintended scope, missed issues, and convention violations.

### 6 — Report

Return a fix summary as structured prose: for each issue, one sentence describing what was changed and why.
