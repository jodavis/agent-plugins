# \<Feature Name\>

> **Status:** Draft
> **Proposal:** \<path/location the user gave for the proposal\> — the proposal this elaborates,
> or "— none"

## Contents

_(Write or regenerate this section last, after every other section is in place, so it reflects
the final heading set rather than a stale mid-draft one.)_

- [Background](#background)
- [Solution](#solution)
- [Success Metrics](#success-metrics)
- [Scope](#scope)
- [User Scenarios](#user-scenarios)
- [Functional Requirements](#functional-requirements)
- [Detailed Behavior](#detailed-behavior)
- [Non-Functional Requirements](#non-functional-requirements)
- [Deliverables](#deliverables)
- [Open Questions](#open-questions)
- [Dependencies](#dependencies)
- [Risks](#risks)

## Background

Brief summary of the problem and goal, linking back to the Proposal named in the header above
rather than re-arguing it. Open with: "Has anything changed since the proposal was approved that
changes the framing?" This section is fact, not opinion — clarify to get it right, but don't
challenge it or offer alternatives to what already exists.

## Solution

A high-level description of the solution, for framing before the section-by-section detail below
— one or two paragraphs on how the pieces hang together.

## Success Metrics

Bring the Proposal's Success Metrics forward and flesh them out with a concrete observability
plan for each — now that the behavior is fully known, how will each metric actually be measured
once this ships (instrumentation, logging, an existing dashboard, a survey, whatever the real
mechanism is)? Open with: "For each metric from the proposal, how will you actually observe it
once this ships?" If a metric turns out not to be observable given the finalized behavior, that's
a real gap — surface it rather than leaving it vague.

## Scope

- **In scope:** ...
- **Out of scope:** ...

Open with: "What's deliberately not covered by this detailed design?" Sharpen the Proposal's
Non-Goals into concrete inclusion/exclusion boundaries now that the behavior is known.

## User Scenarios

Concrete usage scenarios, one per meaningfully different situation. For each, open with: "Walk me
through what happens when...?" A scenario is complete when "does this solve the problem?" can be
checked without guessing — this is where corner cases surface, so keep asking "what about
when...?" until the scenario list stops growing.

## Functional Requirements

Every requirement traces to at least one User Scenario above, and every row must be independently
checkable — a concrete, testable capability, not a general principle. Ask, per scenario: "Who
does this affect, and what can or can't they do?"

Group requirements by user type instead of repeating "As a `<type-of-user>`" in every row: one
`###` sub-heading per type, followed by a table of just the ID, priority, and the capability
(`I <behavior-or-capability>`) for that type.

### As a `<type-of-user>`...

| ID | Priority | I... |
|---|---|---|
| FR-1 | Must | ... |

_(Repeat one `### As a <type-of-user>...` group per user type that has requirements. Only split a
group further into named subsections — e.g. "UI Behaviors," "Preferences" — when the user-type ×
functional-area matrix is large enough that one table per type is still hard to scan; skip
subsections for small requirement sets.)_

A broad guiding principle (e.g. "no user should be able to edit another user's comment") is not
itself a row — state it in one sentence, then let the concrete per-user-type stories that enforce
it be the rows, in whichever user-type group(s) they belong to. Use "Any user" as the type when a
story genuinely applies across all user types.

## Detailed Behavior

Screenshots, specific behavior paths, and corner cases not already covered by User Scenarios.
Open with: "Are there any edge cases or unusual paths through this that aren't obvious from the
main scenarios?"

## Non-Functional Requirements

Standard system requirements: security, performance, accessibility, privacy, compliance. Ask
about each explicitly — confirm with the user which apply and which genuinely don't, rather than
treating silence as "not applicable."

## Deliverables

_(Added by `design-deliverable-breakdown` once the design content above is finalized.)_

## Open Questions

_(Reserved for items the user explicitly deferred, and explicitly agreed should stay open — see
the first-draft skill's interview step. An empty section is the normal, expected outcome.)_

- [ ] Unresolved question

## Dependencies

_(Optional — omit if there are none.)_ Other work this depends on, or that depends on this.

## Risks

_(Optional — omit if there are none.)_ Known risks and how they're being managed or accepted.
