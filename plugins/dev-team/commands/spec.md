---
description: >
  Use when writing a complete new spec for a feature or GitHub issue.
  Guides through context gathering, first draft, iterative refinement, readiness review, and task breakdown.
argument-hint: <work-item-id | #issue | feature name and description> [using <playbook>]
---

Use this skill when:
- A user asks to spec a new feature or GitHub issue
- You need to produce a complete _spec_*.md design document

You are writing a complete new spec, working with the user to refine the spec, breaking down the spec into tasks, and verifying that the spec is complete.

## Steps

### 1 — Resolve the feature brief

Parse `$ARGUMENTS` for a trailing or embedded `using <playbook-reference>` — a path or a bare
installed-skill name — and strip it out before resolving the rest; this may also be given
conversationally rather than as a literal `using` clause. If found, carry `<playbook-reference>`
forward unresolved — `spec-first-draft` resolves it itself in Step 2 below, per
`playbook-contract`'s bare-name resolution order.

Use the `identify-project-work-items` skill to resolve the remaining argument text to a `work-item-id` and `work-item-type`, then fetch the work item:

| `work-item-type` | Action |
|---|---|
| `jira` | Use `work-with-Jira-tasks` to fetch the epic summary and description |
| `github` | Use `work-with-GitHub-issues` to fetch the issue title and body |
| plain text | Use the argument text directly as the feature brief |

If the work item does not exist, tell the user and stop.

### 2 — Write the first draft

Use the `spec-first-draft` skill with the feature brief — and the playbook reference from Step 1,
if one was detected — to gather context from docs, source code, and the user, and write the
draft spec file. When a playbook reference is present, `spec-first-draft` drafts in instance
mode instead of its default flow.

**PAUSE — wait for the user to review the draft.**

### 3 — Refine the spec

Use the `spec-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the document is ready.

### 4 — Design readiness review

Use the `spec-readiness-review` skill on the spec file to verify the design content is implementation-ready.

### 5 — Task breakdown

Use the `spec-task-breakdown` skill to break the spec into tasks, pause for user approval, and create Jira issues.

### 6 — Task breakdown readiness review

Use the `spec-readiness-review` skill again — this time focused on the task breakdown — to verify tasks are scoped and specified clearly enough to implement.

### 7 — Update Jira

Use the `spec-task-work-items` skill to update project work items with summaries of the finalized design decisions.
