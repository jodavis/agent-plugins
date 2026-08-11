# Proposal / Detailed Design Split

> **Status:** Draft
> **Design:** — none. This is meta work on the dev-team plugin's own spec pipeline; the source is
> Jira epic ADR-336 ("PM spec process") directly, not a `_design_*.md` doc or a proposal document
> — no such doc existed for this feature before this dev spec (the pipeline this spec adds is
> exactly what would have produced one).
> **Architecture doc:** `_doc_ProposalDetailedDesignSplit.md` — authored by
> `dev-spec-task-breakdown`'s unconditional final "Author design documentation" task once
> implementation completes; this spec persists afterward for harvesting

## Contents

- [Overview](#overview)
- [Responsibilities & Boundaries](#responsibilities--boundaries)
- [Key Design Decisions](#key-design-decisions)
- [Component Breakdown](#component-breakdown)
- [Planned Implementation](#planned-implementation)
- [Related Features](#related-features)
- [Open Questions](#open-questions)
- [Related Docs](#related-docs)
- [Tasks](#tasks)

## Overview

PR #76 already split the old single-pass spec pipeline into `write-design-spec` (a PM-style
design doc: problem, solution, observable behavior) and `write-dev-spec` (the implementation
"how"). ADR-336 asks for one more split on the PM side: today's single design doc conflates two
things that deserve separate documents — a short **Proposal** that sells the problem and approach
(read by someone deciding whether to fund the work) and a **Detailed Design** that spells out the
desired application behavior in full (read by someone deciding whether the behavior is complete
and correct, and by whoever carves it into shippable deliverables). This feature repurposes the
existing design-doc skills into the Proposal phase, adds a new Detailed Design phase, and rewires
every skill that referenced "the design doc" to know which of the two it means. `write-dev-spec`
and everything downstream of it is unaffected.

## Responsibilities & Boundaries

- **Owns:** the `write-proposal` and `write-detailed-design` commands and their first-draft,
  review, and work-item-sync skills; the handoff between the two new commands and into the
  existing `write-dev-spec`; removing `add-to-spec` (superseded by revise mode — see Key Design
  Decisions); a new `## Contents`
  section added to all three first-draft templates, including `dev-spec-first-draft`'s; a
  re-entrancy ("revise an existing document") mode added to all three commands and all three
  first-draft skills, `write-dev-spec`/`dev-spec-first-draft` included; the new `assets/*.md`
  template-file convention, adopted by all three first-draft skills including
  `dev-spec-first-draft`'s; a new `document-concision-pass` skill, called once from each
  first-draft skill and again as the final step of all three commands including `write-dev-spec`
  — see Key Design Decisions. The Proposal document is deliberately **not** added to the
  `documentation` config schema — see Key Design Decisions.
- **Does not own:** `dev-spec-task-breakdown`, `dev-spec-task-work-items` — unchanged in their own
  content, though `dev-spec-task-work-items` is no longer `write-dev-spec`'s last step (see Key
  Design Decisions). `document-discussion`, `document-readiness-review`, `gather-brief-sources`,
  `identify-project-work-items`, `find-repo-documentation` — already document-type-agnostic,
  reused as-is with no changes. `write-dev-spec`/`dev-spec-first-draft` are otherwise unchanged
  apart from the five deliberate exceptions above (Contents, re-entrancy, template extraction to
  `assets/`, first-draft-time concision call, final concision call) — kept in step with the other
  two commands rather than drifting, per the user's call.
- **Integrates with:** `get-project-configuration` (reads the `documentation` schema; this
  feature extends nothing in it — see Key Design Decisions),
  the work-tracking adapters (`work-with-Jira-tasks`, `work-with-GitHub-issues`) via the renamed
  source-item-sync skill, and `write-dev-spec` as the consumer of the Detailed Design doc.

## Key Design Decisions

### Table of Contents on every spec document

_Context:_ Spec/design/proposal documents get long by the time they're finalized (this document
is itself an example). A per-document, hand-maintained index isn't reliable.
_Decision:_ Add a `## Contents` section — a flat list of `##`-level headings with anchor links —
immediately after the header block, in all three first-draft templates:
`proposal-first-draft`, `detailed-design-first-draft`, and (the one pre-existing template this
feature otherwise leaves alone) `dev-spec-first-draft`. Whichever skill drafts a section writes
or regenerates `## Contents` last, after every other section is in place, so it reflects the
final heading set rather than a stale mid-draft one.
_Consequences:_ This is the one edit this feature makes to `dev-spec-first-draft` — see
Responsibilities & Boundaries above.

### Two commands, with an offer to chain

_Context:_ ADR-336 left open whether this should be one skill run twice or two separate skills.
PR #76 already established the repo's answer to the analogous design/dev-spec split: separate
top-level commands, one handing off to the next.
_Decision:_ Add `/write-detailed-design` as a new command alongside a repurposed
`/write-proposal` (renamed from `/write-design-spec`), mirroring the existing
`write-design-spec` → `write-dev-spec` handoff pattern. Unlike that existing handoff (which just
tells the user the next command to run), `write-proposal` ends by asking the user whether to
continue straight into `write-detailed-design` now or stop and pick it up later — so both the
"one sitting" and "come back later" workflows are first-class.
_Consequences:_ `write-detailed-design` must be able to start cold (resolving its own proposal
input the same flexible way `gather-brief-sources` resolves any source — a file path, pasted
content, or a location the user names — since the Proposal isn't config-tracked; see Key Design
Decisions) as well as be invoked in-line from `write-proposal` with the proposal already in hand
and any related-work-items list already gathered.

### Deliverable breakdown moves to the Detailed Design phase

_Context:_ The existing `design-deliverable-breakdown` skill runs at the end of the (formerly
single) design doc. ADR-336's split raised the question of which new phase should own it.
_Decision:_ Per the user, deliverable breakdown happens after the Detailed Design, not after the
Proposal — deliverables are sized once the actual behavior is known, not from the high-level
approach alone.
_Consequences:_ The `## Deliverables` section (and the `design-deliverable-breakdown` skill that
fills it in) moves from the Proposal doc to the Detailed Design doc. The Proposal's "Proposed
Approach" section may still narrate a high-level phasing plan in prose, but the tracked
feature-work-items themselves aren't created until Detailed Design is approved.
`design-deliverable-breakdown/SKILL.md`'s own stale references — step 1's "the placeholder left
by `design-first-draft`" and step 3's "if `write-design-spec` already gathered a list..." — need
the same mechanical rename sweep as `write-repo-documentation` and `get-project-configuration`
(see below): `design-first-draft` → `detailed-design-first-draft`, and the gathered-list handoff
now comes from the `write-proposal` → `write-detailed-design` chain rather than a single command.

### Document naming: "Proposal" and "Detailed Design"

_Context:_ The epic's author didn't like "one pager" and wanted a different term.
_Decision:_ "Proposal" for the goal/approach/justification document. Unlike every other document
type in this pipeline, the Proposal gets no `_proposal_`-prefix filename convention — that
underscore-prefix convention exists purely so `grep`-based `documentation.*.search` commands can
find a document type scattered across an in-repo tree; since the Proposal isn't repo-tracked by
default (see Key Design Decisions below), that convention doesn't apply to it, and its filename
is whatever the user chooses when `write-proposal` asks where to save it. The second document
keeps the existing "Detailed Design" name and `_design_<Feature>.md` filename/`_design_` pattern
— it's the closer descendant of today's single design doc (it keeps the Behavior section and
gains the Deliverables section), so keeping its name and file pattern minimizes churn. Going
forward, the bare word "design" in this plugin always means "detailed design"; the new, distinct
term is "proposal."
_Consequences:_ No config changes follow from this naming decision — `documentation.specs`
stays as-is (see the config-schema decision below, which is now much smaller than originally
drafted). `detailed-design-first-draft` resolves its file location the same way
`design-first-draft` does today — per `write-repo-documentation`'s configured
`documentation.specs` placement — so it gains `write-repo-documentation` as a dependency (add to
its Component Breakdown row). `write-repo-documentation/SKILL.md`'s "pre-implementation PM-style
design doc (via `design-first-draft`)" line must be updated to say `detailed-design-first-draft`,
since that's now the skill resolving a `documentation.specs` location — `proposal-first-draft`
does not call `write-repo-documentation` at all, consistent with the Proposal asking the user
directly instead of deriving a location from config. Likewise
`get-project-configuration/SKILL.md`'s `documentation.specs` description ("written by
`design-first-draft`") needs the same one-word fix, to `detailed-design-first-draft` — this is a
prose reference to which skill writes there, not a schema change, so it doesn't conflict with "no
config changes" below; that decision is about the YAML schema and `merge_config.py`, not
incidental mentions of which skill uses a key.

### Proposal documents are not part of the `documentation` config schema

_Context:_ Detailed Design and dev-spec docs are committed, in-repo artifacts, discoverable by
grepping `docs/` — that's what `documentation.specs`/`documentation.dev-specs` are for. A
Proposal is pre-decision, not-yet-committed content (it's the "should we even do this"
document); it will most often live outside the repo entirely (a personal notes file, a
Confluence page, a doc tool). Saving it outside version control does cost something — it's
harder to see how it evolved iteration to iteration — but the repo still isn't the right home
for it by default.
_Decision:_ No `documentation.proposals` category is added. `documentation.specs` is **not**
renamed — it keeps describing the Detailed Design doc exactly as it does today (the bare word
"design" in this plugin now means "detailed design," per the naming decision above, so the
existing key name already reads correctly). `write-proposal` asks the user where to save the
proposal (any path or external location they choose) instead of deriving one from config; a user
who wants their proposal tracked in-repo and grep-discoverable is free to save it under `docs/`
themselves, but that's their choice, not a convention this pipeline enforces.
_Consequences:_ No changes to `get-project-configuration`, `update-project-configuration`,
`merge_config.py`, or the default/project-level config YAML. `write-detailed-design` resolves its
proposal input via flexible source-gathering (see the "Two commands" decision above), not a
config-driven search.

### Review skill split: `researcher-proposal-review` and `researcher-detailed-design-review`

_Context:_ ADR-336 asks for tailored reviews: the Proposal should be checked "as a manager
deciding whether to fund it" (problem/solution fit); the Detailed Design should be checked for
corner cases and non-obvious gaps. The existing `researcher-design-review` mixes both concerns
today (problem/solution fit *and* the deliverable-independence check, *and* implicitly
behavior-scenario completeness since Behavior lived in the same doc).
_Decision:_ Rename `researcher-design-review` to `researcher-proposal-review` and trim it to
problem/solution-fit concerns only (falsifiable problem, solution plausibly resolves it — not
just something adjacent, non-goals explicit, alternatives genuinely considered). Add a new
`researcher-detailed-design-review` that owns: user-scenario completeness ("is every scenario
concrete enough to evaluate without guessing," directly answering ADR-336's corner-case ask),
success-metric observability (checked against the Detailed Design's own `## Success Metrics`
section, which brings the Proposal's metrics forward and fleshes each out with a concrete
observability plan — flagging any metric that isn't actually measurable now that behavior is
finalized), requirements-table well-formedness (every row is independently checkable with an
ID/priority/user-story-shaped description grouped by user type, guiding
principles are backed by concrete rows rather than being rows themselves, and every User Scenario
traces to at least one requirement row), and the deliverable-independence check (moved from
`researcher-design-review`'s old step 5,
since `## Deliverables` now lives in this doc).
_Consequences:_ `document-readiness-review` itself needs no changes — it already takes the
researcher-skill name as an argument and is document-type-agnostic.

### Source work item sync generalized across both phases

_Context:_ `design-work-items` today updates the *originating* tracked work item (not a
deliverable) once, after the design doc is finalized. With two phases, the source item's
description should reflect the Proposal after phase one and the fuller picture (Proposal +
Detailed Design + finalized deliverables) after phase two. There likely won't be a tracked
work-item source for the Proposal phase specifically (Proposals aren't config-tracked), but the
same slot may be filled by some other source document — e.g. a Confluence goal — that this
skill's summary-replacement mechanics apply to just as well; a Goal-shaped source would mostly
draw from the Proposal after phase one and pick up the Detailed Design's deliverables after
phase two, same as a Jira/GitHub item would.
_Decision:_ Rename `design-work-items` to `source-work-item-sync` and generalize it to be called
from the end of both `write-proposal` and `write-detailed-design`, each time replacing/updating
the same originating source's description with a summary of whichever docs are finalized so far
(per its existing `replace-description-when`/`update-description-when` config semantics —
unchanged). Actual integration with a non-`work-tracking` source type (e.g. a Confluence goal) is
out of scope here — no adapter for it exists in this repo's config today — but the language above
is deliberately "originating tracked source," not "Jira/GitHub work item," so this skill isn't
assumed to require a `work-tracking`-configured item specifically.
_Consequences:_ One skill instead of two; no new work-tracking concepts introduced by this
feature.

### Section-to-document split, authored as real templates

_Context:_ ADR-336 listed candidate sections without assigning them to a document. The user
confirmed starting from a recommended split, then asked for that split to be turned into actual
templates — standard headers per section, plus an authoring note per section (goal, questions to
ask the user, other details) — written out for real rather than left as a prose section list.
_Decision:_ The Proposal/Detailed Design split is authored as literal document templates, each
with an inline authoring note per section, directly in the skill asset files that
`proposal-first-draft` and `detailed-design-first-draft` read from (see the next decision for the
`assets/*.md` convention this introduces):
[`design-first-draft/assets/proposal_template.md`](plugins/dev-team/skills/design-first-draft/assets/proposal_template.md)
and
[`detailed-design-first-draft/assets/detailed_design_template.md`](plugins/dev-team/skills/detailed-design-first-draft/assets/detailed_design_template.md).
_Consequences:_ This spec no longer carries a separate copy of the section list — the template
files are the source of truth and were authored now, during spec-writing, rather than copied in
later during implementation. Their exact wording is still fine to adjust further once
`proposal-first-draft`/`detailed-design-first-draft` are actually run against a real feature —
these are a starting point, not a frozen contract.

### Conciseness pass as its own skill, run at draft time and again at the end

_Context:_ A section-by-section interview (see the interview-style decision below) tends to
produce verbose first drafts — restated context, hedging, multi-sentence explanations of things
that need one sentence. Humans reading a finished Proposal, Detailed Design, or dev spec should
get the point in a few minutes, not have to skim past padding. But tightening only once, right
after the first draft, misses everything added afterward — `document-discussion` rounds, and (for
Detailed Design) `design-deliverable-breakdown`, and (for dev specs) `dev-spec-task-breakdown`
all add prose of their own with nothing to tighten it again.
_Decision:_ Extract the tightening instructions into a new, standalone, document-type-agnostic
skill, `document-concision-pass`: given a file path, re-read it section by section and tighten it
— cut restated context, redundant hedging, and multi-sentence explanations that could be one
sentence — without dropping any decision, requirement, or scenario. No assumption about which
template produced the file, so it works unchanged on all three document types (and, in principle,
any other markdown document, though wiring it into any workflow beyond this pipeline is out of
scope here — see Consequences). Each first-draft skill calls it once after drafting, in place of
the inline tightening step described in the prior draft of this decision. All three commands —
`write-proposal`, `write-detailed-design`, `write-dev-spec` — call it again as their last step,
after the originating-source-item sync, so the pass also covers everything discussion/breakdown
rounds added afterward.
_Consequences:_ A fifth deliberate, small exception to `write-dev-spec`/`dev-spec-first-draft`'s
"otherwise unchanged" boundary (alongside Contents, re-entrancy, template extraction, and the
first-draft-time concision call) — `write-dev-spec` itself (not just `dev-spec-first-draft`)
gains a step, for symmetry with the other two commands: a final `document-concision-pass` call
after `dev-spec-task-work-items`. The skill's generality — reusable on other generated documents,
including skill files themselves — is a property of how it's written, not a commitment this spec
makes; actually pointing it at anything outside this pipeline (running it ad hoc, on a different
cadence, or against `SKILL.md` files) is left to the user to invoke directly, not orchestrated by
any command here.

### Skill templates extracted to `assets/*.md` files

_Context:_ Today `design-first-draft` and `dev-spec-first-draft` each embed their document
template as a fenced block inline in their own `SKILL.md`, and no skill in this pipeline has a
separate `assets/` template file. The user dislikes the inline pattern and asked for it fixed as
part of authoring the new templates above, rather than filed as a separate follow-up.
_Decision:_ Introduce an `assets/<name>_template.md` convention (matching the existing
[`use-context-file/assets/context_template.md`](plugins/dev-team/skills/use-context-file/assets/context_template.md)
precedent) for all three first-draft skills. The template files themselves —
[`design-first-draft/assets/proposal_template.md`](plugins/dev-team/skills/design-first-draft/assets/proposal_template.md),
[`dev-spec-first-draft/assets/dev_spec_template.md`](plugins/dev-team/skills/dev-spec-first-draft/assets/dev_spec_template.md),
and
[`detailed-design-first-draft/assets/detailed_design_template.md`](plugins/dev-team/skills/detailed-design-first-draft/assets/detailed_design_template.md)
— are authored now, bundled with this spec rather than copied in later, as a deliberate exception
to this pipeline's usual "spec describes, implementation builds" split. Rewiring
[`design-first-draft/SKILL.md`](plugins/dev-team/skills/design-first-draft/SKILL.md) and
[`dev-spec-first-draft/SKILL.md`](plugins/dev-team/skills/dev-spec-first-draft/SKILL.md) step 2
to reference these files instead of inlining the template — and authoring
`detailed-design-first-draft/SKILL.md` itself — happens during implementation, like every other
source change in this spec.
_Consequences:_ A third deliberate, small exception to `dev-spec-first-draft`'s "otherwise
unchanged" boundary (alongside Contents and re-entrancy) — its `SKILL.md` step 2 will point at
`assets/dev_spec_template.md` instead of inlining the template once implemented.
`design-first-draft` and `dev-spec-first-draft` were the only two skills in the pipeline with an
inline template, so no further retrofit is needed elsewhere in the plugin.

### Re-entrancy: revising an existing Proposal, Detailed Design, or dev spec

_Context:_ Today, none of `write-proposal`, `write-detailed-design`, or `write-dev-spec` check
whether a document of their own type already exists before drafting — each assumes "brand new."
But new requirements get discovered and ideas emerge after a document has already shipped.
`gather-brief-sources` already resolves flexible sources (tracked item, pasted notes, file, link,
or a combination), but on its own it doesn't handle a genuinely cross-cutting revision that
ripples across several existing sections at once (e.g. a discovery that changes the Problem
statement _and_ three existing User Scenarios). Initially scoped to just the two new commands,
but folded in for `write-dev-spec` too, to keep it in step with the other two rather than drift —
the same call already made for the Contents decision above.
_Decision:_ All three commands — `write-proposal`, `write-detailed-design`, `write-dev-spec` —
gain a revise mode. After `gather-brief-sources` resolves the brief, each checks whether a
document of its own type already exists for this feature/task (`write-detailed-design`'s own
Step 1, defined below in Planned Implementation, already performs an equivalent check to find its
Proposal _predecessor_; this extends the same idea to each command's own document type —
`documentation.specs.search` for Detailed Design,
`documentation.dev-specs.search` for dev spec, and flexible source-resolution for Proposal since
it isn't config-tracked). If a matching
document is found, the first-draft skill (`proposal-first-draft`, `detailed-design-first-draft`,
or `dev-spec-first-draft`) is invoked in **revise mode**: read the existing document in full,
treat the new brief as the reason for revision, and interview the user section-by-section about
what actually changes — potentially touching several sections, not just appending one bounded
new part. Everything downstream (discuss, readiness review, work-item sync) is unchanged, since
those steps already operate generically on "the document" regardless of how its current draft
came to be. Revise mode now covers `add-to-spec`'s old narrow case too — a single bounded
addition is just a revision that happens to touch one section — so `add-to-spec` is removed
rather than extended; see the next decision.
_Consequences:_ `proposal-first-draft`, `detailed-design-first-draft`, and `dev-spec-first-draft`
each need an explicit "Revising an existing document" step in their `SKILL.md`, alongside "Write
the first draft" — broader than `design-first-draft`'s existing "or a new part of an existing
one" framing, since a revision here may span multiple sections. All three commands need a
re-entrancy check step inserted before "write the first draft." No new Jira epic is needed —
this stays inside ADR-336's scope, as a second deliberate, small exception to `write-dev-spec`'s
otherwise-unchanged boundary (paired with the Contents decision above).

### `add-to-spec` removed, superseded by revise mode

_Context:_ `add-to-spec` existed for one narrow case: appending a single bounded,
work-item-shaped addition to an existing document. Now that all three `write-*` commands have a
revise mode that reads the whole document and interviews holistically about what changed, that
narrow case is strictly a subset of what revise mode already does — a bounded addition is just a
revision that happens to land in one section.
_Decision:_ Remove `add-to-spec` rather than extend it to a three-way branch. Anyone who wants to
add or update something in an existing Proposal, Detailed Design, or dev spec re-runs the
matching `write-*` command, which detects the existing document and enters revise mode.
_Consequences:_ `commands/add-to-spec.md` is deleted. This feature no longer owns an "`add-to-spec`
three-way branch" — removed from Responsibilities & Boundaries, Component Breakdown, and Related
Docs. One fewer entry point; "just re-run write-X" is the single mental model for both revising
and extending a document.

### Conversational, section-by-section interview for Proposal and Detailed Design

_Context:_ The batched approach today (ask up to 4 multiple-choice questions, one optional
follow-up round) works for `dev-spec-first-draft` — a dev spec is about assembling a cohesive,
complete system, not telling a story. Proposal and Detailed Design are different: they walk a
narrative (why → what → how it behaves), which reads better, and is more reliably _complete_,
when gathered section by section in conversation rather than as a batch of disconnected
questions up front. A pure Q&A-and-record interview also risks rubber-stamping a weak problem
statement or an under-considered solution — the agent should read more like a colleague in a
design review than a form-filler.
_Decision:_ `proposal-first-draft` and `detailed-design-first-draft`'s "gather context" step
becomes a section-by-section conversational interview: walk the document's section list in
order; for each section, ask the user an open question about its content (e.g. "What is the
problem you're trying to solve?"), then ask plain-conversation follow-ups — not constrained to
`AskUserQuestion`'s multiple-choice shape — until there's enough to draft that section. When the
agent can infer a likely answer from the brief, prior docs, or research already gathered, it
offers the inferred answer as a suggestion and explicitly asks the user to confirm or correct it
(e.g. "It looks like the problem you're trying to solve is.... Do I have that right?") — it never
assumes an inference is correct. `AskUserQuestion` remains available for genuinely discrete-option
decisions, just not as the default shape of the whole gathering phase. `dev-spec-first-draft`
keeps its current batched-question mechanism unchanged.

The agent does not just record answers — when a section involves a genuine, material trade-off (a
design choice with more than one reasonable approach, or a proposed solution that only partially
addresses the stated problem), it states the alternative(s) and their pros/cons before accepting
the user's choice, and asks probing follow-ups to refine a half-formed answer rather than drafting
from it as-is. This is reserved for points with a real trade-off (scope, cost, risk, UX) — not
reflexive pushback on every answer, which would just be annoying and slow the interview down. One
explicit exception: the Background section (current product/architecture state) is treated as
fact, not opinion, and is never challenged — the agent may ask clarifying questions to get it
right, but doesn't offer alternatives to what already exists.
_Consequences:_ This applies only to the two new skills — see the next decision for how the
underlying "don't silently leave things unresolved" problem is fixed for `dev-spec-first-draft`
too, without changing its interaction style.

### Open questions/TBD markers require explicit user sign-off, in all three skills

_Context:_ `dev-spec-first-draft`'s current step 2 instruction — "for anything genuinely
unresolved, use `> TBD: reason` inline and list it again in Open Questions" — is a silent escape
hatch: the agent decides something is "genuinely unresolved" and defers it, without the gap ever
being surfaced as an askable question. In practice, dev specs routinely finish with Open
Questions the agent could have just asked about during drafting.
_Decision:_ In all three first-draft skills, a TBD/open question is opt-in, not a default. Before
finalizing any draft, if there's a question the agent could ask that would close a gap, it must
ask it — via the section-by-section interview for `proposal-first-draft`/
`detailed-design-first-draft`, or via one explicit confirmation round for `dev-spec-first-draft`
(its existing batched-question mechanism stays otherwise unchanged). A `> TBD`/open question is
only allowed to remain in the finished document when the user has explicitly agreed it should
stay open for now — never a silent default when drafting wraps up.
_Consequences:_ `dev-spec-first-draft` needs no interaction-style change (no section-by-section
rewrite), just a tightened step 2: replace the unconditional "use TBD" language with "confirm
with the user before leaving anything open." This is the fix for the "I could have answered that
if asked" gap, decoupled from the interview-structure question above. `proposal_template.md`
gained an `## Open Questions` section (matching the one the other two templates already had) so a
signed-off-open TBD in a Proposal has somewhere to land — without it, this rule would have nowhere
to record its own exception.

## Component Breakdown

All components in this feature are prompt/config content (skill and command Markdown files, plus
plain YAML), not executable application logic — none carry conditional/iteration logic dense
enough to need dedicated automated verification beyond visual inspection and a dry-run walkthrough
(consistent with every sibling skill in this pipeline: `design-first-draft`, `gather-brief-sources`,
etc. have none today). All rows below are **Wrapper**-tier; verification is a dry-run of the full
`/write-proposal` → `/write-detailed-design` → `/write-dev-spec` chain against a real epic (see the
`harvest-playbook` row in Related Features).

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `write-proposal` (command, renamed from `write-design-spec`) | Wrapper | Orchestrates brief resolution → related-items lookup → proposal draft → refine → review → source-item sync → final concision pass → offer to chain into `write-detailed-design` | `gather-brief-sources`, `identify-project-work-items`, `proposal-first-draft`, `document-discussion`, `document-readiness-review`, `researcher-proposal-review`, `source-work-item-sync`, `document-concision-pass`, `write-detailed-design` |
| `write-detailed-design` (command, new) | Wrapper | Resolves the proposal (cold-start or chained) → drafts detailed design → refine → review → deliverable breakdown → breakdown review → source-item sync → final concision pass → hands off to `write-dev-spec` | `document-discussion`, `document-readiness-review`, `detailed-design-first-draft`, `researcher-detailed-design-review`, `design-deliverable-breakdown`, `source-work-item-sync`, `document-concision-pass` |
| `write-dev-spec` (command, pre-existing; touched to add a final `document-concision-pass` call) | Wrapper | Adds one step after `dev-spec-task-work-items`: a final concision pass over the finished spec, for symmetry with the other two commands | `document-concision-pass` |
| `document-concision-pass` (skill, new) | Wrapper | Re-reads a document section by section and tightens it — cuts restated context, hedging, and multi-sentence explanations — without dropping content; document-type-agnostic | — |
| `proposal-first-draft` (skill, renamed from `design-first-draft`) | Wrapper | Asks the user where to save the proposal, then interviews them and drafts it per `assets/proposal_template.md` | `find-repo-documentation`, `dev-team:researcher` (prior-art research), `document-concision-pass` |
| `detailed-design-first-draft` (skill, new) | Wrapper | Reads the approved Proposal in full, interviews the user, drafts `_design_<Feature>.md` per `assets/detailed_design_template.md` | `find-repo-documentation`, `write-repo-documentation` (file location/naming), `document-concision-pass` |
| `researcher-proposal-review` (skill, renamed from `researcher-design-review`) | Wrapper | Critiques problem/solution fit only | `find-repo-documentation`, `research-learn` |
| `researcher-detailed-design-review` (skill, new) | Wrapper | Checks user-scenario completeness, requirements-table well-formedness (including the user-type grouping and guiding-principle-vs-row distinction), success-metric observability, and deliverable independence | `find-repo-documentation` |
| `source-work-item-sync` (skill, renamed/generalized from `design-work-items`) | Wrapper | Replaces/updates the originating tracked work item's description from whichever doc(s) are finalized so far | (work-tracking adapters, via `get-project-configuration` dispatch) |
| `design-deliverable-breakdown` (skill, unchanged name, updated description) | Wrapper | Adds `## Deliverables` to the Detailed Design doc; creates/reconciles feature-work-items | `get-project-configuration`, work-tracking adapters |
| `dev-spec-first-draft` (skill, pre-existing; touched to add `## Contents` and to extract its template to `assets/dev_spec_template.md`) | Wrapper | Drafts dev specs per `assets/dev_spec_template.md`; adds/regenerates the Contents index last, after all other sections | `document-concision-pass` |

## Planned Implementation

### Interfaces

**Directory/file renames** — every skill in this repo has its directory name exactly equal to its
`SKILL.md` `name:` field, and commands have no `name:` frontmatter at all (a command's name comes
solely from its filename). So the "renamed from" labels used throughout this spec are moves, not
just prose relabeling:

- `skills/design-first-draft/` → `skills/proposal-first-draft/` (its `assets/proposal_template.md`
  moves with it)
- `skills/researcher-design-review/` → `skills/researcher-proposal-review/`
- `skills/design-work-items/` → `skills/source-work-item-sync/`
- `commands/write-design-spec.md` → `commands/write-proposal.md`

The template-file citations elsewhere in this spec that point at `design-first-draft/assets/...`
are lineage notes (today's location of the pre-authored asset), not the final path — they move
along with the directory rename above.

**`write-proposal` command** — argument: `<work-item-id | #issue | feature name and description | pasted notes>` (unchanged from today's `write-design-spec`). New final step:

```
Use AskUserQuestion: "Proposal finalized. Continue now into the detailed design phase, or
stop here and pick it up later with `/write-detailed-design <work-item-id>`?"
  - "Continue now" → invoke write-detailed-design's flow in this same turn, passing the
    proposal path, work-item-id, and the related-existing-work-items list from step 2 if
    still in context.
  - "Stop here for now" → tell the user the resume command and stop.
```

**`write-detailed-design` command** — argument: `<work-item-id | proposal-file-path>` (new
command; also invocable in-line, without re-resolving, from `write-proposal`'s chain step).
Step 1 resolves the proposal:

```
If chained from write-proposal: use the proposal already in hand.
Otherwise: call gather-brief-sources directly to resolve the proposal — a file path, pasted
content, or a location the user names (a URL, a Confluence page, etc.) — since Proposals
aren't config-tracked. There is no documentation.proposals search to fall back on.
If no proposal is found: hard stop. Tell the user a Proposal is required before Detailed
Design — skipping it means skipping the "think about what the solution should be" phase — and
point them to `/write-proposal`. Do not offer to proceed without one.
```

**`documentation` config schema** — unchanged by this feature. `documentation.specs` continues
to describe the Detailed Design doc's location/naming/search exactly as it does today (no new
`proposals` category, no rename — see Key Design Decisions); `architecture` and `dev-specs` are
untouched.

**Proposal document header** (filename is whatever the user chooses when asked where to save it):

```
> **Status:** Draft
> **Source:** <citation(s), or "— none">
```

**`_design_<Feature>.md` header (Detailed Design; filename unchanged):**

```
> **Status:** Draft
> **Proposal:** <path/location the user gave for the proposal> — the proposal this elaborates,
> or "— none"
```

**`_spec_<Feature>.md` header (dev spec; unchanged except wording):**

```
> **Design:** `_design_<Feature>.md` — the detailed design doc this spec implements, or "— none"
```

### Key Classes

Not applicable — no executable classes; see Component Breakdown for the skill/command inventory.

### Data Flow

```
Jira epic / brief
      │
      ▼
/write-proposal  ──(draft, discuss, review)──▶  Proposal doc (user-chosen location,
                                                 outside version control by default)
      │                                                 │  (source-work-item-sync)
      │ [continue now?]                                 ▼
      ▼                                          originating work item description
/write-detailed-design ──(draft, discuss, review)──▶  _design_<Feature>.md
      │                                                 │  ## Deliverables
      │                                                 ▼
      │                                   feature-work-item per deliverable
      │                                                 │  (source-work-item-sync)
      ▼                                                 ▼
 hand off: "/write-dev-spec <deliverable-id>"    originating work item description (updated again)
      │
      ▼
/write-dev-spec (unchanged) ──▶ _spec_<Feature>.md, referencing _design_<Feature>.md
```

## Related Features

| Feature | Scope |
|---|---|
| `write-dev-spec` / `dev-spec-task-breakdown` pipeline | Otherwise unchanged by this feature — only the `> **Design:**` header wording changes (`documentation.specs`, the key it reads, is untouched), plus the five small `write-dev-spec`/`dev-spec-first-draft` exceptions listed in Responsibilities & Boundaries. `dev-spec-task-breakdown` itself is untouched. |
| `harvest-playbook` / `playbook-contract` | Confirmed no references to `_design_*.md`, `documentation.specs`, or `design-first-draft` — no ripple. |

## Open Questions

- [x] Exact wording/fields of the Requirements table's user-story format — resolved: grouped by
      user type (a `### As a <type-of-user>...` heading per group, rows underneath carrying just
      `ID | Priority | I <behavior-or-capability>`), with further named subsections optional for
      large requirement sets. A guiding-principle requirement (e.g. "no user should be able to
      edit another user's comment") is stated in prose, not as its own row — the concrete
      per-user-type stories that enforce it are the rows. See
      [`detailed-design-first-draft/assets/detailed_design_template.md`](plugins/dev-team/skills/detailed-design-first-draft/assets/detailed_design_template.md)'s
      Functional Requirements section for the full template.
- [x] Should `README.md`'s extension-point-skill table and `agents/researcher.md` be updated in
      this same task? Yes for the mechanical part: both reference renamed skills/commands
      (`write-design-spec`, `design-first-draft`, etc.) and need those references updated as
      part of this feature. The table's broader framing (full-file override as a customization
      mechanism) is left as-is otherwise — it's a real but separate staleness issue, tracked at
      [jodavis/agent-plugins#86](https://github.com/jodavis/agent-plugins/issues/86), out of
      scope here.

## Related Docs

- Jira epic ADR-336 ("PM spec process"), jodasoft.atlassian.net
- [`plugins/dev-team/skills/design-first-draft/SKILL.md`](plugins/dev-team/skills/design-first-draft/SKILL.md) — repurposed into `proposal-first-draft`
- [`plugins/dev-team/skills/design-first-draft/assets/proposal_template.md`](plugins/dev-team/skills/design-first-draft/assets/proposal_template.md) — the Proposal template, authored during this spec
- [`plugins/dev-team/skills/detailed-design-first-draft/assets/detailed_design_template.md`](plugins/dev-team/skills/detailed-design-first-draft/assets/detailed_design_template.md) — the Detailed Design template, authored during this spec
- [`plugins/dev-team/skills/dev-spec-first-draft/assets/dev_spec_template.md`](plugins/dev-team/skills/dev-spec-first-draft/assets/dev_spec_template.md) — dev spec template, extracted from `dev-spec-first-draft/SKILL.md`'s prior inline block
- [`plugins/dev-team/commands/write-design-spec.md`](plugins/dev-team/commands/write-design-spec.md) — repurposed into `write-proposal`
- [`plugins/dev-team/skills/design-deliverable-breakdown/SKILL.md`](plugins/dev-team/skills/design-deliverable-breakdown/SKILL.md)
- [`plugins/dev-team/skills/researcher-design-review/SKILL.md`](plugins/dev-team/skills/researcher-design-review/SKILL.md) — repurposed into `researcher-proposal-review`
- [`plugins/dev-team/skills/design-work-items/SKILL.md`](plugins/dev-team/skills/design-work-items/SKILL.md) — repurposed into `source-work-item-sync`
- [`plugins/dev-team/skills/document-discussion/SKILL.md`](plugins/dev-team/skills/document-discussion/SKILL.md), [`document-readiness-review/SKILL.md`](plugins/dev-team/skills/document-readiness-review/SKILL.md) — already document-type-agnostic, reused unchanged
- [`plugins/dev-team/skills/get-project-configuration/assets/default-config.yaml`](plugins/dev-team/skills/get-project-configuration/assets/default-config.yaml), [`scripts/merge_config.py`](plugins/dev-team/skills/get-project-configuration/scripts/merge_config.py) — confirmed schema-agnostic, no code changes needed
- [`plugins/dev-team/commands/add-to-spec.md`](plugins/dev-team/commands/add-to-spec.md) — removed, superseded by revise mode
- [`plugins/dev-team/skills/write-repo-documentation/SKILL.md`](plugins/dev-team/skills/write-repo-documentation/SKILL.md) — its `design-first-draft` reference must become `detailed-design-first-draft`
- [`plugins/dev-team/skills/get-project-configuration/SKILL.md`](plugins/dev-team/skills/get-project-configuration/SKILL.md) — its `documentation.specs` description's `design-first-draft` reference must become `detailed-design-first-draft`
- [`plugins/dev-team/README.md`](plugins/dev-team/README.md) — extension-point skill table references renamed skills
- Commit `90aa862` (PR #76) — established the design/dev-spec split this feature extends
- [jodavis/agent-plugins#86](https://github.com/jodavis/agent-plugins/issues/86) — tracks removing the `.claude/skills/` full-file override escape hatch (out of scope here)

## Tasks

Most tasks below are agent tasks — this feature is entirely prompt/config content (skill and
command Markdown, no application code). Task 1 is the one human-required task. The
`## Related Features` table's two entries (`write-dev-spec`/`dev-spec-task-breakdown` pipeline,
`harvest-playbook`/`playbook-contract`) are "confirmed no ripple" notes, not deferred features to
spec separately — no feature-work-item placeholders created for them.

**Validation strategy:** ADR-380 ("Reimplementing TDD") is the running validation input for every
task below, not just the final dry run (Task 11) — each task's exit criteria include directly
invoking the changed skill(s) (via the `Skill` tool) or command against ADR-380 and confirming the
described behavior actually happens, before moving to the next task. This is a manual operation,
consistent with this feature having no automated test harness (see Component Breakdown).

### Task 1: [[HUMAN] Provide the ADR-380 Proposal source](https://jodasoft.atlassian.net/browse/ADR-386)

**Depends on:** — none —

Create or point to a Proposal-shaped source document for ADR-380 ("Reimplementing TDD") — the
running validation input every task below drafts against. It doesn't need to be a finished,
approved Proposal; it needs to be real enough (a real problem, a real proposed approach) that
`proposal-first-draft` and everything downstream of it has genuine content to work with.

- [ ] A Proposal-shaped source for ADR-380 exists at a location the agent can read (a file path,
      a Jira description, or a pasted-notes location is all fine)

### Task 2: [Author `proposal-first-draft` and `detailed-design-first-draft` together](https://jodasoft.atlassian.net/browse/ADR-387)

**Depends on:** Task 1, Task 5 — both skills' final step calls `document-concision-pass`, so the
validate step below can't actually run end-to-end until Task 5 exists

`git mv skills/design-first-draft/ skills/proposal-first-draft/` (its `assets/proposal_template.md`
moves with it, already authored) and rewrite `SKILL.md`; author new
`skills/detailed-design-first-draft/SKILL.md` against the already-authored
`assets/detailed_design_template.md`. Reviewed together since both run the same interview style
and should stay consistent with each other.

`proposal-first-draft`: ask the user where to save the proposal instead of deriving a location
from config; replace the old inline template/batched-question gathering with a section-by-section
conversational interview (challenge on genuine trade-offs, never on Background); add a "Revising
an existing document" step; replace the tightening instructions with a call to
`document-concision-pass`.

`detailed-design-first-draft`: reads the approved Proposal in full; resolves the file location via
`write-repo-documentation`; runs the same section-by-section interview style; includes a "Revising
an existing document" step; ends with a `document-concision-pass` call.

- [ ] `skills/design-first-draft/` no longer exists; `skills/proposal-first-draft/SKILL.md` and
      `skills/proposal-first-draft/assets/proposal_template.md` exist, `name:` reads
      `proposal-first-draft`
- [ ] `skills/detailed-design-first-draft/SKILL.md` exists with `name: detailed-design-first-draft`
- [ ] Both skills' Step 1 is a section-by-section conversational interview (not batched
      `AskUserQuestion`), with the challenge/pros-cons/probing behavior and the Background
      no-challenge exception, consistently between the two
- [ ] Both have a "Revising an existing document" step alongside "Write the first draft"
- [ ] Neither writes a `> TBD` without explicit user sign-off
- [ ] Both end by calling `document-concision-pass` instead of inlining tightening instructions
- [ ] `proposal-first-draft` has no remaining references to Behavior, Deliverables, or Risks &
      Open Questions sections (trimmed out per the section-to-document split)
- [ ] `detailed-design-first-draft`'s file location/naming resolves via `write-repo-documentation`'s
      `documentation.specs` placement, `_design_<Feature>.md` in PascalCase
- [ ] **Validate:** invoke `proposal-first-draft` against the ADR-380 source from Task 1 and
      confirm it produces a real Proposal doc following the template; then invoke
      `detailed-design-first-draft` against that Proposal and confirm it produces a real Detailed
      Design doc, including its `## Success Metrics` section

### Task 3: [Author `researcher-proposal-review` and `researcher-detailed-design-review` together](https://jodasoft.atlassian.net/browse/ADR-388)

**Depends on:** Task 2

`git mv skills/researcher-design-review/ skills/researcher-proposal-review/` and trim its scope to
problem/solution-fit concerns only (falsifiable problem, solution plausibly resolves it, non-goals
explicit, alternatives genuinely considered) — remove the deliverable-independence and
scenario-completeness checks. Author new `skills/researcher-detailed-design-review/SKILL.md`
checking user-scenario completeness, requirements-table well-formedness (user-type grouping,
guiding-principle-vs-row distinction), success-metric observability (against the Detailed Design's
own `## Success Metrics` section), and deliverable independence (moved from the old skill).
Reviewed together to confirm the split leaves no gap and no overlap between the two.

- [ ] `skills/researcher-design-review/` no longer exists; `skills/researcher-proposal-review/`
      exists with matching `name:` frontmatter, scope limited to problem/solution-fit
- [ ] `skills/researcher-detailed-design-review/SKILL.md` exists, checking user-scenario
      completeness, requirements-table well-formedness, success-metric observability against the
      document's own Success Metrics section, and deliverable independence
- [ ] Between the two skills, every concern from the old `researcher-design-review` is covered
      exactly once — no gap, no duplication
- [ ] **Validate:** run `researcher-proposal-review` against Task 2's ADR-380 Proposal and
      `researcher-detailed-design-review` against its Detailed Design; confirm each returns
      findings scoped only to its own concerns

### Task 4: [Rename & generalize `design-work-items` into `source-work-item-sync`](https://jodasoft.atlassian.net/browse/ADR-389)

**Depends on:** Task 1, Task 2 — validating requires a finalized doc to summarize, and Task 1
only provides raw interview input, not a finalized Proposal

`git mv skills/design-work-items/ skills/source-work-item-sync/`; generalize so it can be called
from the end of both `write-proposal` and `write-detailed-design`, each time replacing/updating
the originating source's description with a summary of whichever docs are finalized so far.
Existing `replace-description-when`/`update-description-when` config semantics are unchanged.

- [ ] `skills/design-work-items/` no longer exists; `skills/source-work-item-sync/` exists
- [ ] Callable after either `write-proposal` or `write-detailed-design` with no document-type
      assumption baked in
- [ ] **Validate:** run `source-work-item-sync` against the ADR-380 source item and confirm its
      description updates with a summary of the finalized doc(s) so far

### Task 5: [Author `document-concision-pass` (new skill)](https://jodasoft.atlassian.net/browse/ADR-390)

**Depends on:** — none —

New, standalone, document-type-agnostic skill: given a file path, re-read it section by section
and tighten it — cut restated context, redundant hedging, and multi-sentence explanations that
could be one sentence — without dropping any decision, requirement, or scenario.

- [ ] `skills/document-concision-pass/SKILL.md` exists, takes a file path argument
- [ ] Makes no assumption about which template produced the file
- [ ] **Validate:** run it against a deliberately verbose sample section (e.g. one of this spec's
      own decisions) and confirm it tightens the prose without dropping any decision or fact

### Task 6: [Update `design-deliverable-breakdown`'s stale references](https://jodasoft.atlassian.net/browse/ADR-391)

**Depends on:** Task 2

Update the description (it now runs against the Detailed Design doc, not the old single design
doc) and fix stale references: step 1's "placeholder left by `design-first-draft`" →
`detailed-design-first-draft`; step 3's "if `write-design-spec` already gathered a list..." → the
`write-proposal` → `write-detailed-design` chain.

- [ ] No remaining references to `design-first-draft` or `write-design-spec` in
      `skills/design-deliverable-breakdown/SKILL.md`
- [ ] **Validate:** run it against Task 2's ADR-380 Detailed Design doc and confirm it drafts
      `## Deliverables` without hitting a stale reference

### Task 7: [Author `write-proposal` and `write-detailed-design` together](https://jodasoft.atlassian.net/browse/ADR-392)

**Depends on:** Task 2, Task 3, Task 4, Task 5, Task 6

`git mv commands/write-design-spec.md commands/write-proposal.md` and rewrite it; author new
`commands/write-detailed-design.md`. Reviewed together since they're a handoff pair and need to
agree on exactly what's passed between them.

`write-proposal`: brief resolution → related-items lookup → re-entrancy check (flexible
source-resolution, since Proposals aren't config-tracked) → `proposal-first-draft` (first-draft or
revise mode) → `document-discussion` → `document-readiness-review` with `researcher-proposal-review`
→ `source-work-item-sync` → `document-concision-pass` → offer to chain into
`write-detailed-design`.

`write-detailed-design`: Step 1 resolves the proposal (use the one already in hand if chained;
otherwise call `gather-brief-sources` directly — no `documentation.proposals` search exists; hard
stop with no proposal found, pointing to `/write-proposal`). Then: re-entrancy check via
`documentation.specs.search` → `detailed-design-first-draft` (first-draft or revise mode) →
`document-discussion` → `document-readiness-review` with `researcher-detailed-design-review` →
`design-deliverable-breakdown` → readiness review on the breakdown → `source-work-item-sync` →
`document-concision-pass` → hand off to `/write-dev-spec <deliverable-id>`.

- [ ] `commands/write-design-spec.md` no longer exists; `commands/write-proposal.md` exists and
      `/write-proposal` is invocable
- [ ] `commands/write-detailed-design.md` exists and `/write-detailed-design` is invocable both
      standalone (`<work-item-id | proposal-file-path>`) and chained from `write-proposal`
- [ ] `write-detailed-design` hard-stops with no proposal found, pointing to `/write-proposal`,
      rather than proceeding
- [ ] Both commands' re-entrancy checks precede drafting
- [ ] `write-proposal`'s final `AskUserQuestion` offers "continue now" (invokes
      `write-detailed-design` in-line, passing the proposal path/work-item-id/related-items list)
      vs. "stop here for now" — and the in-line invocation actually works
- [ ] **Validate:** run `/write-proposal` on ADR-380 end-to-end through the chain-offer, choose
      "continue now," and confirm `/write-detailed-design` picks up with no re-resolution

### Task 8: [Update `dev-spec-first-draft` and `write-dev-spec` together](https://jodasoft.atlassian.net/browse/ADR-393)

**Depends on:** Task 5

Reviewed together to make sure `write-dev-spec`'s updates are comprehensive alongside
`dev-spec-first-draft`'s.

`dev-spec-first-draft`: reference `assets/dev_spec_template.md` (already authored) instead of
inlining the template; add a `## Contents` regeneration note (last, after every section); add a
"Revising an existing document" step; tighten step 2's TBD language to "confirm with the user
before leaving anything open"; end with a `document-concision-pass` call after drafting.

`write-dev-spec`: add a re-entrancy check (`documentation.dev-specs.search`) before drafting; add
a final `document-concision-pass` call after `dev-spec-task-work-items`, for symmetry with the
other two commands.

- [ ] `dev-spec-first-draft` step 2 references `assets/dev_spec_template.md` instead of an inline
      fenced template
- [ ] `dev-spec-first-draft` has a "Revising an existing document" step alongside "Write the first
      draft"
- [ ] `dev-spec-first-draft`'s TBD language requires explicit user confirmation, not a default
- [ ] `dev-spec-first-draft`'s drafting step ends with a `document-concision-pass` call
- [ ] `write-dev-spec`'s re-entrancy check precedes drafting
- [ ] `write-dev-spec`'s `document-concision-pass` call is the last step, after
      `dev-spec-task-work-items`
- [ ] **Validate:** run `/write-dev-spec` against a deliverable (from Task 7's validation run if
      one exists yet, otherwise any throwaway existing spec) and confirm the re-entrancy check and
      final concision pass both actually fire

### Task 9: [Remove `add-to-spec`](https://jodasoft.atlassian.net/browse/ADR-394)

**Depends on:** — none —

Delete `commands/add-to-spec.md` — superseded by revise mode on all three `write-*` commands (see
Key Design Decisions).

- [ ] `commands/add-to-spec.md` no longer exists
- [ ] **Validate:** confirm `/add-to-spec` is no longer a recognized command

### Task 10: [Fix remaining stale cross-references](https://jodasoft.atlassian.net/browse/ADR-395)

**Depends on:** Task 2, Task 3, Task 4, Task 7, Task 9 — the four renames this task confirms
(`design-first-draft`, `researcher-design-review`, `design-work-items`, `write-design-spec`) each
happen in a different task, so this task can't meaningfully validate a rename that hasn't landed
yet. Task 9 is included too: `commands/add-to-spec.md` still contains three of the four stale
names until Task 9 deletes it, and this task's repo-wide grep would otherwise fail on a file it
was never scoped to touch

Sweep: `write-repo-documentation/SKILL.md`'s and `get-project-configuration/SKILL.md`'s
`documentation.specs` descriptions (`design-first-draft` → `detailed-design-first-draft`);
`README.md`'s extension-point skill table; `agents/researcher.md`;
`document-readiness-review/SKILL.md`'s argument-hint example (`researcher-design-review` →
`researcher-proposal-review` or `researcher-detailed-design-review`).

`README.md`'s "Called by" columns need re-deriving from the new call graph, not a literal
find-replace: `write-repo-documentation`'s row becomes `write-detailed-design flow` (not
`write-proposal flow` — `proposal-first-draft` doesn't call it), and `source-work-item-sync`'s row
lists both `write-proposal flow` and `write-detailed-design flow`. `find-repo-documentation`'s row
also gains `detailed-design-first-draft` as a caller, and `researcher-detailed-design-review`
needs its own row if the table doesn't already have a generic "researcher skills" catch-all.

- [ ] No remaining references to `write-design-spec`, `design-first-draft`,
      `researcher-design-review`, or `design-work-items` in `write-repo-documentation/SKILL.md`,
      `get-project-configuration/SKILL.md`, `README.md`, `agents/researcher.md`, or
      `document-readiness-review/SKILL.md`
- [ ] `README.md`'s "Called by" columns reflect the actual new call graph (see above), not a
      mechanical string substitution of the old command/skill names
- [ ] **Validate:** grep the repo for those four names and confirm zero hits outside historical/
      lineage references (e.g. this spec's own "renamed from" notes)

### Task 11: [Dry-run validation of the full chain](https://jodasoft.atlassian.net/browse/ADR-396)

**Depends on:** Task 1, Task 7, Task 8, Task 9, Task 10

Run `/write-proposal` → `/write-detailed-design` → `/write-dev-spec` end-to-end against ADR-380
(per the Component Breakdown's verification note — this feature has no automated test harness).
Fix whatever the dry run surfaces.

- [ ] Full chain runs against ADR-380 without a broken handoff between any two commands
- [ ] Each of the three documents produced matches its template's `## Contents` and section set
- [ ] Re-running `/write-proposal` (or `/write-detailed-design`) against the now-drafted ADR-380
      documents correctly enters revise mode, confirming `add-to-spec`'s removal left no gap

### Task 12: [Author design documentation](https://jodasoft.atlassian.net/browse/ADR-397)

**Depends on:** Task 11

The unconditional final task every `dev-spec-task-breakdown` run appends once implementation
completes (see this spec's own header and `dev-spec-first-draft`'s `> **Architecture doc:**`
line): write `_doc_ProposalDetailedDesignSplit.md` documenting the delivered architecture, per
`write-repo-documentation`'s conventions, so this spec can be harvested afterward. Note in passing:
`dev-spec-task-breakdown/SKILL.md` doesn't yet append this task automatically for future specs —
that's a pre-existing gap in `dev-spec-task-breakdown` itself, out of scope here (this task is
being added by hand, for this spec, same as the convention already describes as the fallback).

- [ ] `_doc_ProposalDetailedDesignSplit.md` exists, following `write-repo-documentation`'s standard
      doc structure
- [ ] It documents the actually-delivered architecture (post dry-run fixes from Task 11), not just
      this spec's original plan
