---
name: fix-pr
user-invocable: false
description: >
  Use when fixing build failures, test failures, or addressing code review comments for a work item with an existing PR.
  Reads the task brief and PR threads, triages each issue, commits fixes one at a time, and returns a fix summary.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You are fixing build failures, test failures, or addressing code review comments
- There is an existing GitHub PR for the work item

You are working with an existing GitHub PR, reading from the workflow context file, fixing issues in existing code, and committing changes locally to the repo.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Read the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the original task brief and work summary from the context file, and ensure the working branch is set up. This context explains what was built and why.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates.

Do not run full validation scripts after making changes — that is the responsibility of another pipeline step. Build and test only the code you modified.

### 4 — Fetch PR issues

Use the `work-with-pr` skill to fetch all open review comment threads from the PR at `pr_url`.

Also fetch any PR check failures so they can be triaged alongside review comments.

### 5 — Triage and fix each issue

Address issues one at a time. For each issue:

**Triage:**

- **Build error:** locate the root cause in the source or test files. Do not patch over symptoms.
- **Test failure:** confirm whether the test itself is correct before touching production code. If the test is wrong, fix the test and explain why in the report. If the test is right, write a failing unit test that isolates the defect, then fix the code.
- **Code review comment:** read the comment and understand the intent.
  - **Agree:** apply the change.
  - **Disagree:** post your rationale as a reply to the PR review thread using `work-with-pr`. Do not apply the change. The Reviewer will evaluate your rationale during sign-off.
  - In either case, always post a reply to the review thread explaining what was done or why nothing was done. Do not resolve the thread — that is the Reviewer's responsibility.

**Fix:**

After each fix, build and test only the project(s) you changed:

```bash
dotnet build <project-path>
dotnet test <test-project-path> --filter "FullyQualifiedName~<ClassName>"
```

If the filter matches zero tests, run the full test project without `--filter`.

**Commit each fix separately** using the `commit-changes` skill with a message describing the specific issue resolved. One commit per issue — do not batch multiple fixes into a single commit.

### 6 — Self-review

Review the diff for unintended scope, missed issues, and convention violations.

### 7 — Report

Return a fix summary as structured prose: for each issue, one sentence describing what was changed and why.
