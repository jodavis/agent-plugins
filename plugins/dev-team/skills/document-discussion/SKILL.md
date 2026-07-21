---
name: document-discussion
user-invocable: false
description: >
  Use when working with the user to refine a document (design doc or dev spec).
  Finds REVIEW comments in the document and resolves them one at a time with the user.
argument-hint: <path to document>
---

Use this skill when:
- You are working with the user to refine a design doc or dev spec
- There are `**Review:**` comments in the document that need to be resolved

## Steps

### 1 — Re-read the document

Read the document in full using the Read tool.

### 2 — Collect review markers

Find all `> **Review:** ...` markers and note any direct edits the user made since the last pass.

If there are no review markers and no edits, tell the user the document has no outstanding comments and ask if they are ready to proceed.

**Method markers are not review comments.** A `> [!NOTE]` / `> **Method:**` callout (defined by
`playbook-contract`) records methodology rationale in flight for later harvesting — it is
structurally distinct from `> **Review:**` markers and has the opposite lifecycle: it persists
until harvest rather than being resolved. Never treat a Method marker as a review comment to
collect in this step, and never resolve or remove one while working through this skill.

### 3 — Resolve each comment

Address review comments **one at a time** in document order:

**a.** Present your analysis of the comment — the trade-offs, your recommendation, and why.

**PAUSE — wait for the user's decision before editing.**

**b.** Update the document to reflect the resolved decision. Remove the `> **Review:**` marker.

**c.** Tell the user what changed, then move to the next comment.

### 4 — Invite another review pass

After all comments are resolved, tell the user:

> All review comments have been addressed. Please review the updated document — add `> **Review:** your comment` anywhere you want a change, or tell me when you're ready to proceed.

**PAUSE — wait for the user.**

Repeat this skill if new review markers appear.
