---
name: document-section-interview
user-invocable: false
description: >
  Use when gathering a document's content section by section against a template, whether drafting
  a new document or revising an existing one with new information. Interviews the user per
  section and enforces that no question is deferred without explicit sign-off.
argument-hint: <template-path> [existing-document-path]
---

Use this skill when:
- A first-draft skill needs to gather section content for a document from the user, following a template's section order
- The document being drafted is a revision of an existing one, not a from-scratch document

Takes the path to the section template and, if revising, the path (or already-read content) of
the existing document. Returns nothing itself — the calling skill uses the resolved answers to
write or update the actual document file afterward.

## Steps

### 1 — Interview section by section

Follow the template's section order. If revising, ask what actually changes in each section — a
revision may touch several existing sections, not just append one bounded new part — rather than
re-interviewing sections that aren't affected. For each section:

- Open with the section's own opening question from the template.
- Follow up in plain conversation — not constrained to `AskUserQuestion`'s multiple-choice shape
  — until there's enough to draft (or update) that section.
- When you can infer a likely answer from the brief, prior docs, or research already gathered,
  offer it as a suggestion and explicitly ask the user to confirm or correct it (e.g. "It looks
  like the problem you're trying to solve is.... Do I have that right?"). Never assume an
  inference is correct.
- On a section with a genuine, material trade-off — a design choice with more than one
  reasonable approach, or a proposed solution that only partially addresses the stated problem —
  state the alternative(s) and their pros/cons before accepting the user's answer, and ask
  probing follow-ups to refine a half-formed answer rather than drafting from it as-is. Reserve
  this for real trade-offs (scope, cost, risk, UX) — not reflexive pushback on every answer.
- **Exception: the Background section is always treated as fact**, not opinion — ask clarifying
  questions to get it right, but never challenge it or offer alternatives to what already exists.

`AskUserQuestion` remains available for genuinely discrete-option decisions; it just isn't the
default shape of the whole gathering phase.

### 2 — Resolve every question before finishing

Treat this skill as the place unresolved questions get eliminated, not deferred. If the calling
skill notices a gap later while writing the draft, come back here rather than carrying the gap
forward into the document's `## Open Questions` section. Before finishing, if there's a question
that would close a gap, ask it. A `> TBD: reason` or an `## Open Questions` entry is only allowed
to remain when the user has explicitly agreed it should stay open (e.g. "I don't know, we'll have
to figure that out as we go") — never a silent default when the interview wraps up, and never for
a question you simply haven't asked yet.
