# Code Review Helper

> **Status:** Draft
> **Proposal:** [Proposal - Code Review Helper](https://jodasoft.atlassian.net/wiki/spaces/AS/pages/4259841/Proposal+-+Code+Review+Helper) (Confluence)

## Contents

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

Reviewing a PR you didn't write — especially in an unfamiliar codebase area — is slow, ad hoc, and prone to approving a change without actually understanding it. See the [Proposal](https://jodasoft.atlassian.net/wiki/spaces/AS/pages/4259841/Proposal+-+Code+Review+Helper) for the full problem statement, goals, non-goals, and prior-art comparison; nothing about that framing has changed since it was finalized.

## Solution

Given a PR reference (number, URL, or work-item ID), the tool resolves it to a single target PR, gathers evidence (diff, related work items, descriptions, existing comments), and creates an isolated branch/worktree for everything that follows. From there, three capabilities are independently invokable rather than a fixed pipeline: a standalone navigation guide (what the PR does, concepts it introduces, questions to answer, a prioritized reading order), a merged report from parallel specialist review passes (code quality, correctness, security, design patterns, testing & coverage), and a comprehension quiz generated straight from the gathered evidence. A reviewer can request any of these alone or together — if requesting both the guide and the report, the guide is generated first; the quiz has no such ordering dependency on either. Findings are published to the PR one at a time, with the reviewer approving, revising, skipping, or discussing each before anything is posted. A separate, author-side entry point reuses the same evidence-gathering and gated-publish mechanics to draft responses to comments other reviewers left on the user's own PR. The reviewer can stop and clean up at any point.

A cross-cutting theme throughout is user control over anything posted on their behalf: every drafted comment, response, or finding is reviewable and revisable before it's sent, and every posted message carries an attribution line naming the tool as its author.

## Success Metrics

Brought forward from the Proposal, with how each will actually be observed:

- **Faster time-to-first-comment** and **repeated use** — self-observed informally; no instrumentation is built for either. This is a personal tool without existing product telemetry, so these are judged by the reviewer's own sense of whether it's faster and whether they keep reaching for it.
- **Quiz catches real gaps** — also self-observed informally: the reviewer notices when a quiz question stumps them or reveals something they missed, rather than the tool tracking quiz outcomes.

## Scope

- **In scope:**
  - GitHub PRs only, reusing this plugin's existing GitHub MCP tooling (`work-with-pr`).
  - Any PR by origin, including PRs the dev-team pipeline itself generated — this tool serves ad hoc human review of any PR, which is a different purpose from the existing `review`/`review-guidelines`/`review-sign-off` skills (automated first-pass review and sign-off for the pipeline's own task-work-item PRs). Both can coexist on the same PR.
  - PR reference resolution by number, URL, or work-item ID (net-new capability — no existing skill in this plugin does this).
  - Independent guide and specialist-report generation, an optional reviewer comprehension quiz, gated per-item publishing with attribution, and an author-side comment-response flow.
- **Out of scope:**
  - Non-GitHub PR platforms (GitLab, Bitbucket, etc.).
  - Auto-approving or merging a PR.
  - Replacing any existing required human or pipeline sign-off/review gate.
  - Quizzing the PR's *author* (only the reviewer is quizzed).
  - Committing test writes/modifications directly to the PR's own branch — they stay in the isolated worktree and surface only as a gated, reviewable finding.
  - Automatic staleness detection when a PR receives new commits mid-review (the reviewer re-invokes manually).
  - Worktree reuse/collision-avoidance logic — every review session gets a fresh, uniquely-named worktree instead.

## User Scenarios

1. **Happy path.** The reviewer points the tool at an unfamiliar PR by number, URL, or work-item ID. The tool resolves the reference, gathers evidence, and creates an isolated worktree. The reviewer requests the guide, reads it, then requests the specialist report. They optionally take the comprehension quiz. They review each finding — publish as-is, revise, skip, or discuss — before anything posts to the PR, each post carrying an attribution line.

2. **Target repo lacks conventions.** The repo the PR lives in has no architecture docs and no configured validation script. The guide is generated without doc citations; the testing & coverage pass runs without a local test suite to execute, and the merged report notes that gap rather than silently omitting it (see Detailed Behavior).

3. **Reviewer revises or discusses a finding.** For any drafted finding, instead of publishing or skipping, the reviewer can ask the tool to revise the wording or discuss it further in conversation before deciding; nothing is posted until the reviewer explicitly approves the (possibly revised) version.

4. **Reviewer aborts and cleans up.** At any point, the reviewer asks to stop. Any running specialist subagents are stopped. If the worktree has uncommitted changes, the tool confirms with the reviewer before discarding them; once confirmed, the branch and worktree are deleted.

5. **PR gets new commits mid-review.** The reviewer notices the PR has moved since evidence was gathered and re-invokes the tool themselves to refresh the guide/report against the new state. There is no automatic detection or prompt.

6. **Author-side: responding to review comments.** The user's own PR has received comments from other reviewers. The user invokes the author-side flow, which reads each comment and drafts a recommended resolution. The user reviews, approves, revises, or skips each drafted response before it's posted — the same gated mechanic as the reviewer-side publish flow.

7. **Concurrent reviews.** The reviewer runs this tool against two different PRs at once (or reviews one PR while the pipeline is mid-task on something else). Each review session gets its own freshly created, uniquely-named worktree — no reuse or collision-avoidance logic is needed since worktrees are never reused across sessions.

8. **Docs-only or narrowly-scoped PR.** The PR only touches documentation or skill prose, with no code changes. Before running the specialist report, the tool recommends skipping specialists that don't apply (e.g. testing & coverage) rather than running all five unconditionally; the reviewer can still add a skipped one back or drop a recommended one before the report runs.

9. **Reviewing specialist value over time.** After running the tool across several PRs, the reviewer wants to know whether every specialist is pulling its weight. They consult the local specialist-outcome log to see, across past reviews, which specialists' findings tend to get published versus skipped, and which specialists' findings duplicate another's — informing a future decision to refine or drop one.

## Functional Requirements

Every requirement traces to a User Scenario above.

### As a Reviewer

| ID | Priority | I... |
| --- | --- | --- |
| FR-1 | Must | can point the tool at a PR by number, URL, or work-item ID and have it resolve to a single target PR |
| FR-2 | Must | can independently request the review guide, the specialist review report, or the comprehension quiz, in any combination or order — if requesting both the guide and the report, the guide is generated first |
| FR-3 | Must | the review guide covers what the PR does, concepts introduced, questions to answer, and a prioritized (non-mandatory) reading order |
| FR-4 | Must | the merged report combines parallel specialist passes (code quality, correctness, security, design patterns, testing & coverage), with duplicate findings on the same location deduped and genuine disagreements between passes surfaced by the merging agent — which may delegate back to a specialist pass to resolve ambiguity — rather than silently resolved by a fixed priority order |
| FR-5 | Should | can take an optional comprehension quiz generated directly from the gathered PR evidence, independent of both the review findings and the guide — no guide or report generation is a prerequisite |
| FR-6 | Must | can review each drafted finding individually and choose to publish as-is, revise it, skip it, or discuss it further before anything is posted |
| FR-7 | Must | every comment or response the tool posts on my behalf carries an attribution line identifying it as tool-drafted |
| FR-8 | Must | can stop and clean up an in-progress review at any time, with confirmation before discarding any uncommitted worktree changes |
| FR-9 | Must | can re-run the review after the PR receives new commits, by re-invoking the tool myself |
| FR-10 | Should | get graceful degradation (skip doc-citing / skip test-running, with the gap noted in the report) when the target repo lacks architecture-doc or validation-script conventions |
| FR-11 | Should | get a recommendation of which specialists apply to the PR's actual content before the report runs, and can override it (add back a skipped one, or drop one) |
| FR-12 | Should | can later review a local log of which specialists ran on past reviews, what each found, and whether each finding was published, revised, or skipped, so I can judge which specialists are providing value versus duplicating each other or finding nothing |

No user of this tool, in either role below, can get it to post, approve, or merge anything without their own explicit per-item approval — see Solution and Non-Functional Requirements.

### As a PR Author

| ID | Priority | I... |
| --- | --- | --- |
| FR-13 | Must | can point the tool at my own PR and get drafted, recommended responses to comments other reviewers left on it |
| FR-14 | Must | can review each drafted response individually and choose to publish as-is, revise it, skip it, or discuss it further before anything is posted — the same gated flow as the reviewer-side publish (FR-6) |

## Detailed Behavior

- **PR reference can't be resolved cleanly** (not found, ambiguous, or access denied): the tool reports exactly what failed and stops. It does not guess at which PR was meant or silently pick a candidate.
- **A specialist review pass fails or errors** (e.g. the testing pass can't run a broken suite): the merge step proceeds with the passes that did succeed, and the merged report explicitly notes which concern couldn't be checked and why. A partial report is produced rather than failing the whole review.
- **All specialist review passes fail or error**: the same principle extends rather than escalating to a hard stop — the merged report is still produced, explicitly stating that no specialist concern could be checked and why, so it reads unambiguously as an incomplete review rather than a clean one.
- **Merge-step conflict resolution**: the top-level merging agent makes the final call on duplicate or disagreeing findings, delegating back to the relevant specialist pass(es) for clarification when needed — never a blind fixed-priority override, and never silently dropping one side of a genuine disagreement.
- **Cleanup with uncommitted changes**: before deleting a worktree that has uncommitted changes, the tool confirms with the reviewer rather than discarding silently.
- **Attribution format**: this design updates the plugin-wide `message-attribution` skill's formatting (used here for FR-7/FR-14, and by every other skill in the plugin that already calls it) rather than introducing a separate mechanism. Every attribution line is italicized, to visually separate it from the rest of the message. A message posted with no human review uses `*Written by <Model>*`. A message that went through a gated per-item review — as every message this design posts always does — uses `*Written by <Model> and reviewed by <Human> before posting*` if published unchanged, or `*Written by <Model> and revised by <Human> before posting*` if the human edited it first. `<Human>` is resolved from a new, explicitly configurable project setting rather than defaulting to the posting GitHub identity — the agent may itself post under its own GitHub account or app identity, distinct from the human actually operating it, which would make a GitHub-identity default nonsensical.

## Non-Functional Requirements

- **Security:** The tool never posts to GitHub without explicit per-item approval from whichever role is operating it, reviewer or PR author (see Functional Requirements). It reuses this plugin's existing GitHub MCP credentials — no new credential surface. All generated artifacts (guide, report, quiz) are written only to the local isolated worktree.
- **Privacy:** PR content — which may include not-yet-public code or business logic — stays local except for whatever the reviewer explicitly approves for publishing as a PR comment. The one exception is the local specialist-outcome log (Deliverable 6) — still local-only, never uploaded or sent anywhere — otherwise no new telemetry or logging pipeline beyond the informal, self-observed metrics in Success Metrics.
- **Performance:** No hard SLA — the parallel specialist passes run as fast as they reasonably can for a personal tool with no enforced time budget.
- **Accessibility / Compliance:** Not applicable — this is a CLI/agent tool for personal use, not a UI product subject to a compliance regime.

## Deliverables

### 1. [PR Reference Resolution & Review Guide](https://jodasoft.atlassian.net/browse/AIP-12)

Resolves a PR reference (number, URL, or work-item ID) to a single target PR, gathers evidence, and creates the isolated worktree every other deliverable builds on — then generates the standalone navigation guide. This is independently valuable on its own: a reviewer gets oriented on an unfamiliar PR (what it does, its concepts, questions to answer, a prioritized reading order) even before any specialist review, quiz, or publish capability exists.

- [ ] Given a PR number, URL, or work-item ID, the tool resolves to exactly one target PR, or reports exactly what failed (not found, ambiguous, access denied) without guessing.
- [ ] An isolated branch/worktree is created before any evidence gathering or guide generation happens.
- [ ] The guide covers what the PR does, concepts it introduces, questions to answer, and a prioritized (non-mandatory) reading order.
- [ ] Guide generation degrades gracefully — skipping doc citations — when the target repo has no architecture docs.
- [ ] The reviewer can stop and clean up an in-progress session at any time; cleanup confirms before discarding any uncommitted worktree changes.

### 2. [Specialist Review Report](https://jodasoft.atlassian.net/browse/AIP-13)

Runs parallel specialist review passes (code quality, correctness, security, design patterns, testing & coverage) against the evidence gathered in Deliverable 1, and merges them into one report. Valuable on its own even without a publish capability — the reviewer gets a complete, multi-concern review report they can act on manually.

- [ ] The report combines findings from all five specialist passes.
- [ ] Duplicate findings on the same location are deduped; genuine disagreements between passes are surfaced by the merging agent (which may delegate back to a specialist pass to resolve ambiguity), never silently resolved by a fixed priority order.
- [ ] If one or more specialist passes fail, the report still generates, explicitly noting which concern(s) couldn't be checked and why — never silently reading as a clean review.
- [ ] The testing & coverage pass runs the repo's local test suite when one is configured, and writes/modifies tests in the isolated worktree (never the PR's own branch) to exercise uncovered edge cases; the report notes when no local suite exists to run.
- [ ] Before running specialist passes, the tool recommends which specialists apply based on the PR's actual content (e.g. skipping a testing pass for a documentation-only change); the reviewer can override the recommendation — add back a skipped specialist or drop one — before the report runs.

### 3. [Gated Publish Flow](https://jodasoft.atlassian.net/browse/AIP-14)

Adds the ability to selectively publish Deliverable 2's findings to the PR as real GitHub comments — one at a time, with revise/skip/discuss options and attribution. Builds on Deliverable 2's findings but delivers distinct new value: turning a report the reviewer previously had to act on manually into directly-posted PR comments, under full per-item control.

- [ ] Each finding can be published as-is, revised, skipped, or discussed further before anything is posted.
- [ ] Every comment the tool posts carries an attribution line in the updated `message-attribution` format (see Detailed Behavior): italicized, with wording that distinguishes published-as-is from revised-before-posting.
- [ ] Nothing is ever posted without the reviewer's explicit per-item approval.

### 4. [Comprehension Quiz](https://jodasoft.atlassian.net/browse/AIP-15)

A standalone quiz generated directly from the evidence gathered in Deliverable 1, independent of both the guide and the specialist report. Lets a reviewer verify their own understanding of a change — catching the "skimmed and approved it" failure mode — without needing to have run either other capability first.

- [ ] The quiz can be requested without generating the guide or the specialist report first.
- [ ] Quiz questions are drawn from the PR's actual change content, not from any review findings.

### 5. [Author-Side Comment Response Flow](https://jodasoft.atlassian.net/browse/AIP-16)

A separate entry point, for when the user is the PR's author rather than its reviewer: reuses Deliverable 1's evidence-gathering and Deliverable 3's gated-publish mechanics to draft recommended responses to comments other reviewers left on the user's own PR.

- [ ] Given the user's own PR, each unresolved comment from other reviewers gets a drafted, recommended response.
- [ ] Each drafted response can be published as-is, revised, skipped, or discussed further before anything is posted.
- [ ] Every posted response carries an attribution line in the updated `message-attribution` format (see Detailed Behavior).

### 6. [Specialist Outcome Tracing](https://jodasoft.atlassian.net/browse/AIP-17)

A local log, built on Deliverable 2's specialist passes, recording which specialists ran on each review, what each found, and the eventual disposition (published, revised, or skipped) of each finding. Independently valuable once enough review history accumulates: it turns "which specialists are actually worth running" from a guess into something the reviewer can check.

- [ ] Each review session logs, locally, which specialists ran and what each one found.
- [ ] The log records each finding's eventual disposition — published, revised, or skipped.
- [ ] The reviewer can review the accumulated log across past reviews to spot specialists whose findings are rarely published or consistently duplicate another specialist's.
- [ ] The log stays local — never uploaded or sent anywhere, consistent with NFR Privacy.

## Open Questions

None.

## Dependencies

- This plugin's existing GitHub MCP tooling (`work-with-pr`) for reading PR diffs/comments and posting reviews.
- The `message-attribution` skill, updated per this design's Detailed Behavior (italicized formatting, automatic-vs-reviewed-vs-revised wording, and a new configurable human-identity setting) — this is a change to a plugin-wide shared skill, so every other skill that already calls it inherits the new formatting too, not just this feature.
- A net-new PR-reference-resolution capability (number/URL/work-item ID → single PR) — does not exist yet in this plugin.

## Risks

- **Cost/latency of parallel specialist subagents** per review — accepted; no SLA is enforced (see Non-Functional Requirements).
- **Agent-drafted tests could assert tautologically** against current, possibly-buggy behavior — mitigated by test writes staying local to the isolated worktree and surfacing only as a gated finding through the same per-item publish approval as any other finding, never committed automatically (see Scope).
- **The `message-attribution` format change has plugin-wide blast radius**: every other skill that already calls it (commit messages, PR reviews, work-item comments) picks up the new italicized, automatic-vs-reviewed-vs-revised format and the new human-identity setting too, not just this feature's own messages — worth a deliberate look at those call sites when this ships, not just this feature's own.
