# Location Flexibility for Planning Documents

> **Status:** Draft
> **Proposal:** Confluence page "Location Flexibility for Planning Documents" (space AS, pageId
> 5570727) — https://jodasoft.atlassian.net/wiki/spaces/AS/pages/5570727/Location+Flexibility+for+Planning+Documents

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

## Background

Today, planning documents (Proposals, Detailed Designs, Dev Specs) are assumed to be repo-local
markdown files, discovered via a `search` shell command that greps file content for an embedded
`<work-item-id>`. This breaks for multi-repo features (no single repo owns the spec) and
work-for-hire repos (the author doesn't want personal planning notes committed into a client
repo), and blocks any project keeping these docs in an external tool like Confluence. Skills
throughout dev-team (`read-task-brief`, `read-dev-spec-section`, `document-discussion`) assume
local file access with no resolution step, with one partial exception: `read-dev-spec-section`
already caches a grep-discovered `spec_path` in the context file.

## Solution

A document's location resolves to one of a bounded set of supported *kinds* — a filesystem path
(repo-relative or not) or a supported external service (Confluence first). Each kind has its own
adapter skill that knows how to fetch, mirror locally, and write back content and comments for
that kind; every other skill (`write-proposal`, `document-discussion`, `read-task-brief`,
`read-dev-spec-section`, etc.) goes through a shared **resolve-and-mirror** step instead of
assuming a local path or running its own grep. That step determines the location and kind (from
project config for `specs`/`dev-specs`, or from whatever the user gave `write-proposal`/
`write-detailed-design` for Proposals/Detailed Designs), fetches/mirrors the content to a local
scratch path if it isn't already local, and records the resolved local path so later steps in the
same task don't re-resolve. `document-discussion` becomes kind-aware too: a Confluence-backed
document's "review comments" are the adapter reading/writing Confluence's native inline comments
instead of grepping the mirrored markdown for `> **Review:**` lines.

Project config is per-*category* (`specs`/`dev-specs`), not per-*task* — it can't say which
specific document belongs to a given work item. For a **repo-local** document, discovery stays
exactly as it is today: grep repo content for the embedded work-item-id. For anything
**non-repo-local**, grep can't reach it, so the tracked work item itself becomes the durable
anchor: when `write-dev-spec`/`write-proposal`/`write-detailed-design` creates or links such a
document, it records a structured marker (`**Document Location:** <kind> <path-or-url>`) in the
work item's description — the same description-update call `source-work-item-sync` (Proposals,
Detailed Designs) and `dev-spec-task-work-items` (dev specs) already make, just with one more
line. This works identically for Jira and GitHub, since neither this
environment's connected Jira MCP tools nor GitHub's issue model expose a native "arbitrary URL"
remote-link primitive as a discoverable tool; a Jira "remote issue link" was considered but
rejected once it was confirmed the connected tools only support reading remote links
(`getJiraIssueRemoteIssueLinks`), not creating them. On first resolve for a task, `spec-finding`
reads the work item's description, parses the marker, and only then mirrors the content and
caches the resulting local path in the context file for the rest of the task.

A document can also have **no tracked work item at all** — e.g. an ad hoc Proposal authored via
`gather-brief-sources`' "no source item" path. In that case there is nothing to look up by
work-item-id in the first place: the caller already has the location directly (the path/URL the
user gave `write-proposal`, or one passed straight to `document-discussion`), so resolve-and-mirror
runs from that given location without ever querying a work item. This is what FR-10 covers, and
it's a distinct case from FR-13 (discovering a location from a work-item-id when only the id is
known) — a document either arrives with a known location, or its location is discoverable from its
work-item-id; there's no third case where neither is true and it still resolves.

Concretely, the existing `spec-finding` state (`FindSpecStep` in `dev_team.py`) — which already
runs immediately before `planning` in the `/implement` pipeline (`workflow-orchestrate`), and
today inline-resolves `spec_path` via grep with no agent dispatch — is the pipeline's own
resolve-and-mirror step: inline for a repo-local path (plain grep, no agent, no tool grant
needed), or a dispatch to a narrowly-scoped agent holding just the location-adapter tools
(Confluence MCP, etc.) for a Confluence-kind result — see below for why this dispatch exists only
here and not in the interactive commands. Every downstream step (`planning`, `implement`,
`review`, ...) reads the resolved path and needs
no location-adapter tool grants at all — this is the whole reason the step exists as its own seam
rather than being inlined into every consumer.

The narrowly-scoped-agent-dispatch pattern is specific to this pipeline context, where downstream
agents (`planner`, `developer`, `reviewer`) must never hold location-adapter tools (FR-9). The
interactive `write-proposal`/`write-detailed-design`/`write-dev-spec`/`document-discussion`
commands are different: they run in a session that already legitimately holds whatever MCP tools
are connected to the environment (as this very design conversation did by hand), so they call the
same adapter mechanics directly and inline — fetch/mirror on read, guarded overwrite on
write-back, native comment read/reply for the review round — with no separate dispatch step. A
location is often already known directly in these commands rather than needing discovery:
creating a new document means the location is already in hand from the creation call itself, and
revising an existing Proposal/Detailed Design means the user gave `write-proposal`/
`write-detailed-design` the location directly (per that command's own "does a Proposal already
exist" step). `write-dev-spec`'s own "check for an existing dev spec" step is the exception: like
`/implement`'s `spec-finding`, it starts cold with nothing but a work-item-id, so it reads the
same work-item-description marker to discover a non-repo-local location — just without the agent
dispatch, since its own session already holds the tools it needs.

## Success Metrics

Brought forward from the Proposal, with a concrete observability plan for each:

- **A document of any category, located outside the repo entirely, can be drafted, reviewed, and
  (for dev specs) implemented end to end.** Observed via a fixture-based integration test — the
  same scripted-fixture-harness pattern already used for `run-hook-instructions`
  (`plugins/dev-team/fixtures/run-hook-instructions/`), not `pytest` — that points a task's
  document location outside the repo and runs the pipeline through to completion.
- **The `write-*` authoring skills can run their review round end-to-end against a
  Confluence-hosted document, using native comments in place of inline markdown.** This is the
  mechanized version of what this very design conversation already did by hand (fetch → mirror →
  edit → write back → reply to native comments). Verified manually against a live Confluence page
  when the Confluence-adapter deliverable ships, and periodically thereafter — no CI automation
  against live Confluence (no stored credentials, no dedicated reset-to-known-state test space).
- **No step re-runs location discovery after the initial resolve.** `FindSpecStep.handle_results()`
  already has this guarantee structurally today (`if ctx.spec_path: return "spec_found"`, an early
  return before any fetch runs) — the generalized resolve-and-mirror step keeps the same
  early-return shape for its own resolved-location field. Observed via the same fixture as Metric
  1: the fixture's mocked location-adapter call is asserted to fire at most once across a
  multi-step run. No new production logging/instrumentation is needed.

## Scope

- **In scope:**
  - Generalizing `FindSpecStep`/`spec-finding` in `workflow-orchestrate` into a resolve-and-mirror
    step: inline (grep, no agent) for repo-local paths; dispatches to a narrowly-scoped agent
    holding location-adapter tools for external kinds.
  - Widening `documentation.specs`/`documentation.dev-specs` config to declare a location *kind*
    (filesystem path or Confluence) alongside today's `location`/`name-format`/`search`.
  - A Confluence location adapter: fetch a page into a local mirror; write local edits back with
    an expected-version guard (see Detailed Behavior); read/reply to native inline comments for
    the review round.
  - Generalizing `document-discussion` to dispatch per resolved location kind — inline
    `> **Review:**` markdown handling for local files, Confluence native-comment read/reply
    otherwise.
  - A persistent, queryable link between a tracked work item and its non-repo-local document's
    location — a structured marker in the work item's description, the same one Jira and GitHub
    both already support reading/writing — replacing embedded-id grep as the discovery mechanism
    wherever grep can't reach.
  - Widening the context file's `spec_path` field (and equivalent state for Proposals/Detailed
    Designs) to hold non-repo-relative and mirrored-local paths.
  - Per-invocation location-kind inference for Proposals/Detailed Designs (outside the
    `documentation` config schema), inferred from whatever location the user gives
    `write-proposal`/`write-detailed-design`.
  - Automated conflict reconciliation/merge for concurrent Confluence-side edits — sequenced as
    its own dedicated deliverable, after the core location-flexibility deliverables (mechanism not
    designed yet; see Open Questions).
- **Out of scope:**
  - Any external service besides Confluence (Google Docs, Notion, etc.).
  - The `documentation.architecture` category.
  - Automatically migrating/relocating documents already at some location today.
  - Granting location-adapter MCP tools (Confluence, etc.) to any pipeline agent other than the
    one the resolve-and-mirror step dispatches — that's the whole point of the new step.

## User Scenarios

1. **Multi-repo dev spec.** A feature spans repos A and B. `write-dev-spec` places the spec at a
   path outside either repo. `/implement` is later run from repo A's checkout; the
   resolve-and-mirror step fetches/mirrors that spec locally into repo A's task workspace before
   planning starts.
2. **Work-for-hire client repo.** The author works in a client-owned repo and doesn't want
   personal planning notes committed there. `write-proposal` saves the Proposal to a local path
   outside the repo (e.g. under the author's home directory); nothing about the client repo's git
   history changes.
3. **Confluence-hosted Proposal, full review round.** `write-proposal` creates a Confluence page.
   The review round happens via native Confluence comments; `document-discussion`'s adapter reads
   them, resolves each with the user, and writes updates back to the page.
4. **Confluence-hosted dev spec through `/implement`.** A dev spec lives on Confluence. The
   resolve-and-mirror step (running once, before `planning`) fetches it into a local mirror and
   writes that path to the context file. `planner`, `developer`, `reviewer` all read the mirrored
   local file — none of them are ever granted Confluence tools.
5. **Status quo: repo-local spec.** A project never opts into any non-default location.
   `spec-finding` behaves exactly as it does today — inline grep, no agent dispatch, no behavior
   change. (Regression guard, not new behavior.)
6. **Ad hoc document with no tracked work item.** A Proposal is authored via `gather-brief-sources`'
   "no source item" path and saved to a chosen location. Later, `document-discussion` is invoked
   directly against that same location to continue the review round — resolve-and-mirror runs from
   the given location; no work-item-id lookup happens because there's no work item to look up.
7. **Concurrent external edit during a task.** A dev spec is Confluence-hosted; someone edits the
   live page after the resolve-and-mirror step already mirrored it locally for a running task. The
   task keeps using its already-mirrored copy for the rest of that run — the concurrent edit isn't
   picked up until a fresh resolve (e.g. a new task). If that same task later writes back to the
   page, the expected-version guard (Detailed Behavior) catches the conflict at write time rather
   than silently overwriting the intervening edit.

## Functional Requirements

### As a project maintainer...

| ID | Priority | I... |
|---|---|---|
| FR-1 | Must | can declare, per `specs`/`dev-specs` category in config, a location kind of either a filesystem path (as today) or Confluence, without changing any other field's shape |
| FR-2 | Must | see no behavior change when I don't declare a kind — the category behaves exactly as it does today (repo-relative path + grep search) |

### As a document author...

| ID | Priority | I... |
|---|---|---|
| FR-3 | Must | can give `write-proposal`/`write-detailed-design` a Confluence space/page as the save location, and it creates the document there instead of asking for a repo-relative path |
| FR-4 | Must | can give `write-proposal`/`write-detailed-design` a filesystem path outside the current repo, and it saves there without requiring the path be under the repo root |
| FR-5 | Must | have my local edits to a revised Confluence-hosted document written back to the same page, guarded against clobbering a concurrent external edit |
| FR-12 | Must | have a non-repo-local document's location automatically recorded as a structured marker in the tracked work item's description when I create or link it — no separate manual step |
| FR-14 | Must | can run `write-dev-spec` against a non-repo-local dev spec and have it discover the existing document's location from the work-item-id via the description marker, the same way `/implement`'s pipeline does — its own grep-based check stays as the repo-local fallback |

### As a reviewer/commenter...

| ID | Priority | I... |
|---|---|---|
| FR-6 | Must | can leave feedback as native Confluence comments on a Confluence-hosted document, and `document-discussion` picks them up the same way it picks up inline markdown review markers |
| FR-7 | Must | see a reply posted to my comment thread summarizing how it was resolved |

### As a pipeline agent (planner/developer/reviewer)...

| ID | Priority | I... |
|---|---|---|
| FR-8 | Must | read a task's document from a local path already resolved by an earlier pipeline step, with no need to know what kind of location it came from |
| FR-9 | Must | am never granted a location-adapter MCP tool (e.g. Confluence) just because a task's document might be hosted externally — only the resolve-and-mirror step's own agent holds it |
| FR-13 | Must | can discover a non-repo-local document's location on first resolve purely from the work-item-id, by reading the work item's description marker — no grep, no guessing |

### As any user...

| ID | Priority | I... |
|---|---|---|
| FR-10 | Must | see a document with no explicit work-item link resolve and mirror the same way a linked one does — link tracking and location resolution are independent |
| FR-11 | Must | see the resolve-and-mirror step run at most once per task run — every later step reads the same already-resolved local path |

## Detailed Behavior

- **MCP tool not connected/authorized when the resolve-and-mirror step needs it.** Attempt the
  call; on an auth-needs-refresh error, trigger the environment's own reauth flow once (the same
  `mcp_auth` recovery-retry pattern `work-with-Jira-tasks` already uses, per
  `_doc_WorkflowEventHooks.md`) and retry the same call exactly once. If it still fails, surface it
  directly to the user and ask them to reauthorize, rather than silently falling back or failing
  the whole pipeline.
- **Write-back to Confluence fails** (permission revoked mid-task, network error, or an
  expected-version mismatch). Surfaces as an ordinary failed step — no silent partial state; the
  local mirror still has the edits, so nothing is lost, but the task doesn't proceed as if the
  write succeeded.
- **Document creation vs. document reading are different paths.** Resolve-and-mirror only applies
  to reading an already-existing document (e.g. the `/implement` pipeline fetching a dev spec that
  already exists). Creating a brand-new document (`write-proposal` targeting a not-yet-existing
  Confluence page) goes directly through the authoring skill's own adapter call — it never goes
  through the pipeline's resolve-and-mirror step.
- **Two tasks resolving the same document concurrently.** Each task mirrors its own independent
  local copy; nothing shared or locked between them. The write-back call includes the page's
  version number captured at mirror time, so Confluence itself rejects the write if the page
  changed since — a silent clobber becomes a visible, safe failure. For this increment, the task's
  user resolves the conflict manually (re-fetch, reapply edits, retry); automated
  reconciliation/merge is a separate, later-sequenced deliverable (see Open Questions).
- **No location marker found for a non-repo-local document.** Grep can't fall back here (there's
  nothing local to grep for a non-repo-local kind). `spec-finding` reports failure the same way
  today's repo-local discovery already does when nothing matches — "no document found for this
  work item" — rather than guessing a location.
- **Mirror file lifecycle.** The local mirror lives in the task's own state directory (alongside
  the context file), not a shared or temp location, and isn't auto-deleted when the task finishes
  — consistent with how context files already persist after a task.

## Non-Functional Requirements

- **Security:** least-privilege boundary on location-adapter MCP tools — see FR-9.
- **Performance:** mirroring adds one network round-trip per task, not per step — that's the point
  of FR-11.
- **Privacy:** mirrored local files may contain content pulled from an external service
  (Confluence) onto local disk, in the task's state directory. Not a repo commit (state directory
  is outside the repo), so this doesn't leak into git history.
- **Accessibility:** not applicable — internal agent-pipeline mechanism, no UI.
- **Compliance:** not applicable beyond what's already covered by the work-for-hire scenario
  (Scenario 2), which this design supports rather than conflicts with.

## Deliverables

### 1. Filesystem-path location flexibility

Lets a Proposal, Detailed Design, or Dev Spec live at any filesystem path — in the repo, outside
it, or shared across repos — instead of only a repo-relative path. Delivers Scenarios 1
(multi-repo), 2 (work-for-hire), 5 (status-quo regression guard), and 6 (ad hoc, no tracked work
item) entirely on its own, with no dependency on Confluence support. No new agent dispatch is
needed here — a non-repo-local filesystem path is still a plain local read/copy, so `spec-finding`
stays inline.

- [ ] `documentation.specs`/`documentation.dev-specs` config accepts a location outside the repo
      root, not just a repo-relative path.
- [ ] `write-proposal`/`write-detailed-design` accept a filesystem path outside the current repo
      as the save location.
- [ ] The context file's `spec_path` field (and equivalent state for Proposals/Detailed Designs)
      holds non-repo-relative paths correctly.
- [ ] A non-repo-local document's location is recorded as a structured marker in the tracked work
      item's description (via `source-work-item-sync` / `dev-spec-task-work-items`) and
      discovered from it on first resolve, with no grep involved. This covers both cold,
      work-item-id-only discovery paths: `/implement`'s `spec-finding` (which then dispatches per
      Deliverable 2 for a Confluence-kind result) and `write-dev-spec`'s own "check for an
      existing dev spec" step (today a plain `documentation.dev-specs.search` grep), which reads
      the marker directly and inline — no dispatch needed, since `write-dev-spec` already runs in
      a session holding whatever tools are connected, the same as `write-proposal`.
- [ ] A project that never opts into a non-default location sees no behavior change.

### 2. Confluence location adapter (fetch, mirror, guarded write-back)

Lets a Proposal, Detailed Design, or Dev Spec live on Confluence and be fetched/mirrored/written
back to, from both the `/implement` pipeline and the interactive `write-*` commands. Delivers
Scenario 4 (Confluence-hosted dev spec through `/implement`), the document-creation half of
Scenario 3, and the write-back/conflict-safety half of Scenario 7 — all independent of whether
native-comment review automation (Deliverable 3) exists yet, since a Confluence-hosted document
can already be reviewed by hand (as this very design conversation did).

- [ ] `documentation.specs`/`documentation.dev-specs` config accepts Confluence as a location
      kind.
- [ ] `write-proposal`/`write-detailed-design`/`write-dev-spec` can create a new Confluence page
      directly as the save location.
- [ ] `spec-finding` generalizes into the resolve-and-mirror step for the `/implement` pipeline:
      repo-local paths stay inline; a Confluence-kind location dispatches to a narrowly-scoped
      agent that fetches and mirrors the page locally, then writes the resolved path back to the
      context file. No pipeline agent other than this one is ever granted Confluence MCP tools.
- [ ] `write-proposal`/`write-detailed-design`/`write-dev-spec`/`document-discussion`, run
      interactively, can fetch/mirror/write back a Confluence document given an already-known or
      marker-discovered location directly and inline — no dispatch step,
      since the invoking session already holds whatever tools are connected.
- [ ] A local edit to a mirrored Confluence document writes back to the same page, and a
      write-back is rejected (not silently applied) if the page's version changed since it was
      mirrored.
- [ ] An MCP auth failure during a fetch or write-back triggers one reauth-and-retry attempt
      before surfacing to the user.

### 3. Confluence-native review round

Lets the review/discussion round for any `write-*` authoring skill run entirely through
Confluence's native comments instead of inline `> **Review:**` markdown, for a document
fetched/mirrored under Deliverable 2. Delivers the review-automation half of Scenario 3, turning
what this design conversation did by hand into an automatic capability.

- [ ] `document-discussion` dispatches per location kind: inline markdown handling for local files
      (unchanged), native Confluence comment read/reply otherwise.
- [ ] A Confluence comment is picked up, resolved with the user, and answered with a reply
      summarizing the resolution — with no inline markdown markers involved.

### 4. Confluence conflict reconciliation

Removes the "resolve it yourself" friction from Deliverable 2's expected-version write guard by
automatically reconciling a concurrent Confluence-side edit instead of just failing safely.
Depends on Deliverable 2 already existing; delivers standalone value on top of it (task authors no
longer have to manually re-fetch/reapply/retry on a conflict).

- [ ] A write-back that would otherwise fail on a version mismatch is instead reconciled
      automatically, without data loss and without requiring the task's user to manually
      intervene.
- [ ] The specific reconciliation mechanism (diff/merge strategy, any UI) is designed as part of
      this deliverable's own `write-dev-spec` pass — it is intentionally undesigned here (see Open
      Questions).

## Open Questions

- [ ] Automated conflict-reconciliation mechanism for concurrent Confluence-side edits (diff/merge
  strategy, any UI) — deferred to its own dedicated deliverable; not designed yet, tracked so it
  gets a work item under AIP-10.
