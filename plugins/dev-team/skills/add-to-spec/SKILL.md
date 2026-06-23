---
name: add-to-spec
description: >
  Use when writing a new part of an existing spec.
  Identifies the target spec, drafts the new section, refines with the user, verifies readiness, and updates the Jira task.
argument-hint: <Jira task key | brief description of the new requirement>
---

Use this skill when:
- You are adding a new requirement or task to an existing spec
- You need to draft a new section of a `_spec_*.md` file

You are writing a new part of an existing spec, working with the user to refine the spec, breaking down the spec into tasks, and verifying that the spec is complete.

## Steps

### 1 — Identify the work item and target spec

Use the `identify-work-item` skill to get the `work-item-id`.

Use the `work-with-Jira-tasks` skill to fetch the Jira task. Determine the target spec from the task's parent epic. If the target spec is not obvious, ask the user which spec to add to.

### 2 — Read the target spec

Read the spec file in full. Note: existing tasks, task numbering, insertion point, and patterns (checklist format, Gherkin scenarios, exit criteria structure).

### 3 — Draft the new content

Use the `spec-first-draft` skill focused on the new section. Provide the existing spec context so the draft follows established patterns and is inserted at the correct position.

The draft should include:
- Any new spec sections needed
- The new task entry: `### Task N — <title> ([<work-item-id>](<url>))`
  - One-paragraph description
  - Checklist exit criteria
  - Gherkin acceptance scenarios for observable behaviour
- Any exit criteria that must be added to other tasks based on patterns this task establishes

**PAUSE — wait for the user to review the draft.**

### 4 — Refine the new content

Use the `spec-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the content is ready.

### 5 — Readiness review

Use the `spec-readiness-review` skill on the full spec file. The researcher reviews the full spec (not just the new task) to check cross-task consistency as well.

### 6 — Update the Jira task

Use the `work-with-Jira-tasks` skill to update the Jira task description with a summary of the finalized content:

- One-paragraph overview of what this task implements
- Bulleted list of key decisions and their outcomes
- Reference to the spec section: `See spec: <relative path>`

Replace the original description entirely rather than appending.
