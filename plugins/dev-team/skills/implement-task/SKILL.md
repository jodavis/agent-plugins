---
name: implement-task
user-invocable: false
description: >
  Use when implementing a task from a task brief.
  Reads the task brief, loads developer standards, implements using TDD, commits, and returns a work summary.
argument-hint: <work-item-id | context-file>
---

Use this skill when:
- You need to implement a task from a task brief
- You are writing new code for a work item

You are reading the workflow context file to find a task brief, writing new code to implement the task brief, and committing changes locally to the repo.

## Steps

### 1 — Identify the work item

Use the `identify-work-item` skill to determine the `work-item-id` from the user's input or conversation context.

### 2 — Get the task brief

Use the `read-task-brief` skill with the `work-item-id` to load the task brief and ensure the working branch is set up.

### 3 — Load developer standards

Use the `developer-standards` skill to load code guidelines and quality gates.

**IMPORTANT**: In this workflow, full validation is the responsibility of another agent. Build and test only the code you modified — do not run the full validation suite.

### 4 — Understand the task

Read the task brief in full. Identify:

- The exit criteria — these define what "done" means
- Files to create or modify, and the design decisions that constrain each
- Existing utilities, base classes, and patterns to reuse (the brief will call these out)

If anything in the brief is ambiguous and the ambiguity would affect correctness, note it in your work summary and resolve it conservatively.

### 5 — Implement

Use the `test-driven-development` skill to implement the task.

### 6 — Commit

Use the `commit-changes` skill to commit all changes with a clear message.

### 7 — Self-review

Review the diff as if you were doing a code review:

- Does every exit criterion have demonstrable coverage (code + test)?
- Are there missing test cases (branches, error paths, invalid inputs)?
- Do all files follow the standards loaded in step 3?
- Is there any scope creep — changes not required by the brief?

### 8 — Report

Return a work summary as structured prose:

**Files created or modified**
List each file by path with a one-line description of what changed.

**Key decisions made**
Anything not dictated by the brief that you chose during implementation (design choices, interface splits, tradeoffs). Omit this section if there are none.

**Unit tests**
File path(s) and test method names for all new or modified unit tests.

**E2E scenarios**
Feature file path(s) and scenario title(s) for all new or modified Gherkin scenarios.
