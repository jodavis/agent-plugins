---
name: document-concision-pass
user-invocable: false
description: >
  Use when a document needs a final tightening pass. Re-reads it section by section and cuts
  restated context, redundant hedging, and multi-sentence explanations that could be one
  sentence — without dropping any decision, requirement, or scenario.
argument-hint: <path to document>
---

Use this skill when:
- A document has just been drafted or extended and its prose has accumulated padding
- You are running a final tightening pass before a document is considered done

Takes one argument: the path to the document. Makes no assumption about which template (or
whether any template) produced it — this skill works unchanged on a Proposal, a Detailed
Design, a dev spec, a `SKILL.md` file, or any other markdown document.

## Steps

### 1 — Re-read the document

Read the document in full using the Read tool.

### 2 — Walk it section by section

Split the document into its headings (each `##` block; use `#` blocks instead if the document
has no `##` headings, or a nested `###` block where a `##` section is long enough that tightening
it as a whole would be unwieldy). Working in document order, for each section:

**a.** Re-read just that section's text.

**Leave callout blocks untouched.** A `> [!NOTE]` / `> **Method:**` callout (defined by
`playbook-contract`) records methodology rationale in flight for later harvesting, and a
`> **Review:**` callout marks an open review comment — both are structurally distinct from
ordinary prose and depend on their exact marker syntax for later grep-based/agent recognition.
Skip both entirely in steps b–c: never reword, merge, or otherwise tighten a `> [!NOTE]` /
`> **Method:**` or `> **Review:**` blockquote block.

**b.** Look for concision opportunities within it:
- Restated context the reader already has from an earlier section or from the section's own
  heading
- Redundant hedging ("it's worth noting that", "in general", a qualifier repeated more than
  once) that doesn't change the meaning
- A multi-sentence explanation that says no more than a single sentence would

**c.** Tighten the section's wording with `Edit`. Cut only wording — never remove, merge away, or
soften a decision, requirement, or scenario the section states. When in doubt whether a sentence
is padding or load-bearing content, leave it as is.

**d.** If the section needs no changes, move on without editing it.

### 3 — Confirm nothing was lost

Compare the tightened document against the full text read in step 1: every decision,
requirement, and scenario present before must still be present — reworded is fine, dropped is
not. If a cut in step 2 turns out to have removed something substantive, restore it (reworded, if
that still reads more tightly than the original) before finishing.
