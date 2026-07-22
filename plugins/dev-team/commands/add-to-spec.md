---
name: add-to-spec
description: >
  Use when writing a new part of an existing design doc or dev spec.
  Identifies the target document and its type, drafts the new content, refines with the user, verifies readiness, and updates tracked work items.
argument-hint: <work-item-id | #issue | brief description of the new requirement>
---

Use this skill when:
- You are adding a new requirement, deliverable, or task to an existing design doc or dev spec
- You need to draft a new section of a `_design_*.md` or `_spec_*.md` file

You are writing a new part of an existing document — either a PM-style design doc or a dev spec —
working with the user to refine it and verifying that it is complete. Which document type you're
extending changes the drafting, review, and work-item-update steps used, but not the overall shape
of this flow.

## Steps

### 1 — Resolve the target document and its type

Use the `gather-brief-sources` skill to resolve the argument into a `work-item-id` (if any) and a
brief describing the new content.

Determine which document type covers the target:

- If the user already said which kind (design doc or dev spec), use that.
- Otherwise, substitute the `work-item-id` into `documentation.specs.search` (design doc); if
  found, that's the target.
- Otherwise, substitute it into `documentation.dev-specs.search` (dev spec); if found, that's the
  target.
- If neither search finds anything, ask the user which document to add to, and which kind it is.

### 2 — Read the target document

Read the document in full. Note: existing sections/tasks/deliverables, numbering, insertion
point, and established patterns (checklist format, Gherkin scenarios, exit criteria structure).

### 3 — Draft the new content

- **Design doc target** → use the `design-first-draft` skill focused on the new content (a new
  behavior scenario, or a new deliverable). Provide the existing design doc's context so the
  draft follows established patterns and is inserted at the correct position.
- **Dev spec target** → use the `dev-spec-first-draft` skill focused on the new section. Provide
  the existing spec's context so the draft follows established patterns and is inserted at the
  correct position. The draft should include:
  - Any new spec sections needed
  - The new task entry: `### Task N — <title> ([<work-item-id>](<url>))`
    - One-paragraph description
    - Checklist exit criteria
    - Gherkin acceptance scenarios for observable behaviour
  - Any exit criteria that must be added to other tasks based on patterns this task establishes

**PAUSE — wait for the user to review the draft.**

### 4 — Refine the new content

Use the `document-discussion` skill to resolve `> **Review:**` comments with the user.

Repeat until the user says the content is ready.

### 5 — Readiness review

Use the `document-readiness-review` skill on the full document — with `researcher-design-review`
for a design doc, or `researcher-dev-spec-review` for a dev spec. The researcher reviews the full
document (not just the new content) to check cross-section consistency as well.

### 6 — Update the tracked work item

- **Design doc target** → use the `design-work-items` skill to update the source work item (if
  any).
- **Dev spec target** → use the `dev-spec-task-work-items` skill to update the work item with a
  summary of the finalized content:
  - One-paragraph overview of what this task implements
  - Bulleted list of key decisions and their outcomes
  - Reference to the spec section: `See spec: <relative path>`

  Replace the original description entirely rather than appending.
