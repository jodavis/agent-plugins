# TDD for Implementation

> **Status:** Draft
> **Will become:** `_doc_TddForImplementation.md` once implementation is complete
> **Feature-work-item:** [ADR-288](https://jodasoft.atlassian.net/browse/ADR-288)

## Overview

Establishes a component taxonomy — **Wrapper**, **Testable**, and **Orchestrator** — that the
dev-team pipeline uses to decide how thoroughly a piece of code needs to be tested, and a
tightly constrained **`tdd-tester` / `tdd-implementer` / `tdd-refactorer`** ping-pong protocol
that drives strict TDD for the Testable tier. The
taxonomy is introduced during spec drafting (a new Component Breakdown section), carried
through task planning (component-aware task briefs), and executed during implementation (the
Developer agent becomes an orchestrator that spawns these three new sub-agents per component).
This replaces the current single-agent, component-at-a-time flow in `test-driven-development`
with a disciplined red/green/refactor loop, while leaving the top-level pipeline (`dev_team.py`,
`workflow-orchestrate`) completely unaware that any of this happened — it's all internal
to the Developer's "implementing" step.

## Responsibilities & Boundaries

- **Owns:**
  - The Wrapper / Testable / Orchestrator component taxonomy and its definitions
  - The new `## Component Breakdown` section in the spec template (`spec-first-draft`)
  - Component annotations added to task briefs (`plan-task`, `write-task-brief`)
  - The TDD ping-pong protocol (`tdd-tester` / `tdd-implementer` / `tdd-refactorer`) and its
    termination conditions
  - TDD practice rules (AAA structure, red-must-fail-for-the-right-reason, frozen
    Arrange/Act after first Assert, test naming convention) as standardized dev-team
    conventions, folded into `tdd-practices` and `code-change-expectations`
  - Three new agent definitions, each defined primarily by what it is *not allowed* to touch:
    `agents/tdd-tester.md` (test files only), `agents/tdd-implementer.md` (production files
    only), `agents/tdd-refactorer.md` (behavior-preserving changes only)
  - The Developer agent's revised role: orchestrator of the trio for Testable components;
    direct implementer for Wrapper and Orchestrator components
  - The three-way implementation skill split: `implement-task` (dispatcher, per-component
    branching), `implement-direct` (single-shot direct implementation), `implement-tdd`
    (ping-pong orchestration for one Testable component)
  - The Researcher agent's revised role: component-aware task planning — determining which
    components a task touches, their tiers, and dependency order
- **Does not own:**
  - The pipeline state machine, JSON descriptor protocol, or `workflow-orchestrate` loop
    (ADR-269/277) — unchanged; this feature is entirely internal to the existing
    `implementing` step
  - `developer-standards` / project-specific style rules (`.editorconfig`, `CONTRIBUTING.md`)
    — these still take precedence over the default naming convention introduced here
  - Implementation-time behavior when a harness is missing — `missing-test-harness` still
    governs that case; this feature only adds the design-time decision of whether to build
    one (see Key Design Decisions)
- **Integrates with:**
  - `spec-first-draft` — gains a Component Breakdown authoring step
  - `plan-task` / `write-task-brief` — task briefs gain a "Components in scope" section
  - `implement-task` — rewritten as a dispatcher that invokes `implement-direct` or
    `implement-tdd` per declared component, then triages any remaining exit-criteria work
    (component-shaped but uncaptured, or genuinely not component-shaped) before a final
    commit; `test-driven-development` is retired — its E2E-testing wrapper moves to the new
    `behavior-driven-development` skill and its TDD practice rules move to the new
    `tdd-practices` skill; its old per-component "write tests then implement" procedure is
    removed outright, not carried into either
  - `code-change-expectations` — coverage checklist gains logging as a testable concern
  - `missing-test-harness` — a Testable component with no fitting verification mechanism
    becomes its own Component Breakdown line item (build the harness), rather than an
    implementation-time improvisation
  - `agents/developer.md` — role updated to describe the orchestrator responsibility
  - `agents/researcher.md` — role updated to describe component-aware task planning
  - `commit-changes` — invoked once per component (not once per task) during implementation
  - Eight new files: `agents/tdd-tester.md`, `agents/tdd-implementer.md`,
    `agents/tdd-refactorer.md`, `skills/implement-direct/SKILL.md`, `skills/implement-tdd/SKILL.md`,
    `skills/component-taxonomy/SKILL.md`, `skills/behavior-driven-development/SKILL.md`,
    `skills/tdd-practices/SKILL.md` — the latter two replacing the retired
    `skills/test-driven-development/SKILL.md`

## Key Design Decisions

### Component taxonomy: Wrapper / Testable / Orchestrator

_Context:_ Not all code needs the same testing rigor, and treating everything identically
either wastes effort on trivial pass-through code or under-tests the code that actually
carries logic. The epic proposes three tiers based on where correctness risk actually lives.

_Decision:_ Every planned component is classified as exactly one of:

- **Wrapper** — a thin call-through to a system component or library, simple enough that
  visual inspection is sufficient. No dedicated unit test is written for it. This tier also
  applies at the property/method level within a Testable or Orchestrator component: an
  individual member that's a simple call-through or straightforward translation — no
  conditional or iteration logic — is Wrapper-tier in its own right, even though the
  component around it isn't. Agents shouldn't spend turns testing simple properties or
  pass-through methods just to pad out coverage.
- **Testable** — owns logic, isolated from its dependencies via dependency injection. This
  is where TDD-style verification applies in full. "Testable" names a tier of *risk*, not a
  specific mechanism — most Testable components are verified with the tdd-tester/tdd-implementer
  ping-pong protocol against unit tests, but some carry the same logic risk without fitting
  Arrange-Act-Assert unit tests (agent-skill prose is the clearest example in this repo).
  Those are still Testable; they're verified by whatever mechanism actually fits (e.g.
  evals), under the same red/green, one-behavior-at-a-time discipline.
- **Orchestrator** — wires Testable/Wrapper components together. Can carry some complexity,
  but simple integration tests (not full unit TDD, not a paired ping-pong) are enough to
  flush out wiring bugs. An integration test here exercises the Orchestrator wired to its
  real, non-mocked direct dependencies (the Wrapper/Testable components it depends on),
  written in the same test project/framework as everything else, covering the Orchestrator's
  primary wiring scenario end-to-end. It's scoped to just this one Orchestrator and its
  direct dependencies — narrower than the cross-component E2E scenarios that already re-run
  at the end of `implement-task`.

This taxonomy classifies production components; it doesn't apply to test-only code (test
fixtures, builders, mock factories, custom assertions and the like). Those aren't given a
tier and don't get a dedicated test of their own by default — they're exercised naturally by
every test that uses them, which is normally coverage enough. If a particular piece of test
infrastructure is complex enough to warrant direct unit tests of its own, that's a reasonable
judgment call to make, but it's a nice-to-have, not something Component Breakdown authoring
or `code-change-expectations` needs to require.

_Consequences:_ Test effort concentrates on the components that carry real logic, and design emphasizes isolating logic in testable components. Authors
must think about component boundaries before writing code, which is why the taxonomy is
captured at spec time, not implementation time. Component Breakdown authoring asks two
separable questions per component: does it carry logic risk at all (Wrapper vs. not), and
— if so — what verification mechanism actually fits it (see below for what happens when
none exists yet).

These definitions live in a new shared `component-taxonomy` skill rather than only in this
spec's prose — see "Work outside classified components" below for why (Developer's ad hoc
triage needs the identical definitions a spec author uses, not a second copy).

---

### Component Breakdown section added to the spec template

_Context:_ Task planning and implementation both need to know, ahead of time, what components will be built or modified, what tier each belongs to, and how they depend on each other — otherwise the developer must judge for itself what needs paired TDD.

_Decision:_ `spec-first-draft` gains a new `## Component Breakdown` section, authored
alongside `Planned Implementation`. Format:

| Component | Type | Responsibility | Depends on |
|---|---|---|---|
| `<Name>` | Wrapper \| Testable \| Orchestrator | One sentence | `<Component>`, `<Component>`, or — |

When identifying Testable components, apply these isolation patterns as authoring guidance
(not enforced mechanically, but stated in the skill instructions):

- Prefer dependency injection for isolating a component from its collaborators.
- Consider the **State Object** pattern for stateful components: state lives as
  directly-observable fields on a plain data object. By default, only the owning/controller
  service mutates it — other services may read it, but write access is reserved for the
  owner, so there's exactly one place responsible for driving valid transitions. Some
  components legitimately invert this — a ViewModel-style State Object is written directly
  by its consumer (e.g. the UI), and the owning controller subscribes to change
  notifications on it to react — but even then, exactly one side owns a given kind of
  change; the "one clear place transitions happen" property still holds, just in the other
  direction. Either way, because state is always plain, directly observable data, a test can
  arrange a hard-to-reach starting state by constructing/setting the object directly, and
  can assert the post-state by reading it directly — without indirectly inferring internal
  state through side effects.
- Prefer synchronous logic for anything complex; do async work up front (e.g. gathering all data needed for a process) and pass the results into the complex process, rather than doing async work on demand within the process, requiring the entire process to be async.
  Async testing is expensive (this repo's own `CONTRIBUTING.md` async test-pattern section
  is a direct illustration of that cost) — complex logic belongs in synchronous, easily
  tested components. This also avoids bouncing between threads when the complex work needs to stop and resume repeatedly.
- Where practical, implement each component before its dependencies are built, using mock implementations of the interfaces, so the
  dependency interfaces reflect real usage rather than speculative design.

_Consequences:_ Spec authors (with researcher support, per existing `spec-first-draft` flow)
must think architecturally before task breakdown. `spec-readiness-review` should treat a
missing or insufficient Component Breakdown as a blocking gap when the spec describes any
Testable-tier logic — insufficient meaning: a component the spec's own text describes isn't
listed in the table, a "Depends on" entry names a component that isn't in the table at all,
or (per the next decision) a Testable component with no identified verification mechanism
and no harness-building line item covering the gap.

---

### Missing verification mechanisms are scoped at design time, not improvised during implementation

_Context:_ `missing-test-harness` forbids inventing a new test harness "unless explicitly
instructed," to stop an implementer from silently bolting one on, unreviewed, as a side
effect of an unrelated task. But mandating TDD for every Testable component means some
target projects will have Testable-tier code with no existing verification mechanism at
all — and simply falling back to no testing (Wrapper treatment) would defeat the purpose.

_Decision:_ Whether a Testable component needs a new verification mechanism built is decided
during spec drafting, not implementation. While authoring the Component Breakdown, the spec
author checks each Testable component against the target project's existing verification
tooling. If nothing fits, the mechanism itself becomes its own line in the Component
Breakdown (type `Testable`, e.g. "Eval harness for skill-prose verification" or "Unit test
scaffolding for `<area>`"), with its own dependency edges so components that need it depend
on it. That line flows into task breakdown as explicit, reviewed scope — a task to build the
harness, sequenced before the components that depend on it.

`missing-test-harness` continues to govern the implementation-time case unchanged: an
implementer mid-task must still not invent a harness on the fly. If it discovers a gap the
spec missed, that's a spec gap to flag back, not something to work around silently.

_Consequences:_ `spec-readiness-review` should treat a Testable component with no identified
verification mechanism, and no harness-building line item covering the gap, as a blocking
gap — the same check already called for above, made concrete. "No identified verification
mechanism" is checked the same way `missing-test-harness` already checks it (searching for
existing test-file patterns in the target project) — just run by the researcher during spec
review, against the target project as it exists today, rather than by the developer mid-task.
Building a harness is never a surprise mid-implementation; it's either already scoped as its
own line item or the spec is incomplete.

---

### Task briefs carry a component subset in dependency order

_Context:_ A task typically touches a subset of the spec's components. The developer needs
to know, for just that subset, each component's tier and the order dependencies force it to
build them in.

_Decision:_ `write-task-brief` gains a new section, **Components in scope**, derived from the
spec's Component Breakdown filtered to the components this task touches, and listed as a
flat, topologically-sorted list — a component always appears after everything it depends on.

```
## Components in scope

1. `TokenCache` — Testable — depends on: —
2. `AuthOrchestrator` — Orchestrator — depends on: `TokenCache`
```

**Components in scope can legitimately be empty.** Not every task touches a classified
component at all — e.g. scaffolding a new project from a template and tailoring it isn't
Wrapper, Testable, or Orchestrator work, it's project setup. This is different from the
no-Component-Breakdown fallback below in cause (a spec with a full taxonomy where this one
task just doesn't touch any of it, vs. a spec with no taxonomy at all) but not in effect:
either way, `implement-task` falls through to the triage described in "Work outside
classified components" below, rather than skipping TDD outright — an empty list doesn't mean
the task has no logic worth testing, only that none of it was pre-classified.

_Consequences:_ `plan-task` no longer needs a separate ordering step — the sort is computed
once, during brief writing, from data already captured in the spec.
`agents/researcher.md`'s role description is updated to state this responsibility
explicitly, directly satisfying the epic's mandate that the researcher be aware of
components and which need TDD. This ordering is also exactly what a future
parallel-execution optimization would need (independent components are the ones with no
path between them in this order) — but Developer doesn't exploit that today; see the next
decision.

---

### Developer becomes the orchestrator; tdd-tester, tdd-implementer, and tdd-refactorer are new sub-agents; implement-task splits into a dispatcher and two skills

_Context:_ The epic calls for "two agents, an implementer and a tester" per Testable
component; a dedicated refactor pass is a standard part of TDD that the epic doesn't rule out
and this design adds explicitly (see the protocol decision below). The existing pipeline only
spawns one `dev-team:developer` agent for the entire `implementing` step. Introducing more
top-level pipeline agents (and routing turn-by-turn messages through the already-lean
`workflow-orchestrate` loop) would leak a large number of turns into the top-level
orchestrator's context, which the loop was specifically designed to avoid
(`workflow-worker`'s one-line return contract exists for exactly this reason).

_Decision:_ The Developer agent's `implementing` step is unchanged from the pipeline's point
of view — one `spawn_agent` action, one work summary returned. Internally, `implement-task`
splits into three skills:

- **`implement-task`** — the dispatcher. For each component in the task brief's Components in
  scope list, in dependency order, invokes `implement-direct` (Wrapper, Orchestrator) or
  `implement-tdd` (Testable).
- **`implement-direct`** — Developer implements a component itself, in its own turn: no
  pairing, no sub-agents. Used directly for Wrapper/Orchestrator components, and reused by
  `implement-tdd` whenever a Tier 2 escalation (below) resolves to `resolve_directly` — so
  "Developer implements something itself" has exactly one definition, not two.
- **`implement-tdd`** — orchestrates one Testable component's ping-pong protocol. Developer
  uses the `Agent` tool to spawn one `tdd-tester`, one `tdd-implementer`, and (after the pair
  reaches `done`) one `tdd-refactorer` sub-agent, driving them through the protocol below
  using `SendMessage` to continue each sub-agent's conversation turn by turn.

Developer implements components one at a time, in the dependency order captured in the task
brief's Components in scope list — a component's dependencies are always fully committed
before the next component starts. This is a deliberate simplification: true concurrent
implementation would need per-component isolation (e.g. separate worktrees) to stop one
component's build break from corrupting another's test run — a real risk for compiled
languages — and this pipeline optimizes for correct, unattended autonomous operation over
wall-clock speed. Revisiting parallel execution, using the dependency ordering already
captured in the task brief, is future work, not pursued now.

_Consequences:_ No changes to `dev_team.py`, the JSON descriptor protocol, or
`workflow-orchestrate`. Three new agent definitions are needed, each scoped by a hard
constraint on what files it may touch rather than by a loose job description — this is what
makes protocol violations mechanically detectable (see below). Two new skills
(`implement-direct`, `implement-tdd`) are needed alongside a rewritten `implement-task`
dispatcher. The Developer agent's role description changes materially — it is now also an
orchestrator, mirroring the very Orchestrator tier this spec defines for target-project code.
This design takes a real dependency on `SendMessage` for turn-by-turn sub-agent resumption —
a capability no existing dev-team agent uses today, since every current `Agent`/`Task` call
in this plugin is fire-and-forget. Confirmed available: `SendMessage` (`to`/`message`/
`summary` parameters; addresses a named teammate or a background agent's `agentId`) is a
live tool in the current Claude Code environment this pipeline runs in — verified directly
rather than assumed. No fallback is needed.

---

### TDD ping-pong protocol: tdd-tester, tdd-implementer, tdd-refactorer

_Context:_ "Taking turns" needs a concrete, terminating choreography — how the next behavior
is chosen, how a red test is guaranteed to fail for the right reason rather than a build
break, how disagreements get resolved without stalling, and how the design gets cleaned up
once it's green — all while keeping Developer's own context cheap across what is expected to
be a large number of turns. Reviewing an independent TDD agent-harness prototype (ping-pong
role responsibilities, a dedicated refactor phase, and a behavior-selection rubric) surfaced
useful shape for this choreography; the pieces adopted below are adapted, not copied, to fit
this pipeline's autonomy and one-line-per-turn context-cost constraints — notably, this
design drops that reference's declared-expected-result contract and edge-case-first ordering
in favor of the alternatives explained inline.

_Decision:_ Three narrowly constrained roles participate per Testable component:

- **`tdd-tester`** — only ever edits test files. Adds exactly one new behavior per turn (one
  new test method, one new case on an existing parameterized test, or one new `Assert`
  appended to an existing, Arrange/Act-frozen method). Never touches production code.
- **`tdd-implementer`** — only ever edits production files. Makes the smallest possible
  change that satisfies the current red assertion — the "dumbest thing that could possibly
  work" — never a generalized solution that happens to also cover untested cases. Never
  touches test files.
- **`tdd-refactorer`** — only ever makes behavior-preserving changes, to either test or
  production code. Runs after every real green during the loop — the "refactor" third of a
  genuine red-green-refactor cycle, not a single pass deferred to the end — never after a
  `structural-green` (no real behavior exists yet to clean up) and never against a component
  with a failing test.

Each role's file-scope constraint is mechanically checkable: a `tdd-tester` diff that touches
a production file, or a `tdd-implementer` diff that touches a test file, is a protocol
violation Developer can detect directly from the changed-file list at the end of a turn —
Developer gets that list via `git diff --name-only` (or the target project's VCS equivalent)
immediately after each turn.

`tdd-tester`, `tdd-implementer`, and `tdd-refactorer` build and run tests using the same
tool and command syntax already documented in `code-change-expectations` for the target
project (e.g. `dotnet build` / `dotnet test --filter`) — no new build/test convention is
introduced. Every red/green turn keeps this as
cheap as possible: an incremental build (never a full clean rebuild) and a test run scoped to
just the component under test (a single test, or that component's suite — see "The loop"
below), never the full project suite. The full project suite is reserved for whatever point
in the existing pipeline already runs it (e.g. the E2E re-run after all components are
implemented); it doesn't run on every TDD-loop turn.

Developer tracks the `agentId` returned when it spawns each of the three sub-agents for a
component (via the `Agent` tool) for as long as that component is being implemented, and
addresses `SendMessage`'s `to` field with the matching id to continue that specific
sub-agent's turn. A fresh trio is spawned per Testable component; ids from a finished
component aren't reused.

**Choosing the next behavior** (`tdd-tester`'s decision each turn), in order:
1. One externally observable behavior at a time. Skip any member that is itself Wrapper-tier
   (a simple call-through/translation with no conditional or iteration logic, per the
   taxonomy decision above) — these don't need dedicated coverage just because they live
   inside a Testable component. A log statement inside an otherwise-trivial member doesn't
   change that (see "Logs are a testable concern" below).
2. Express it as one new assertion, choosing the cheapest structural fit:
   - If a parameterized/data-driven test with the identical Arrange/Act shape already
     exists, add a new case to it.
   - Otherwise, if the scenario's Arrange/Act genuinely doesn't differ from an existing
     (non-parameterized) frozen method, append a new `Assert` to that method.
   - Otherwise, write a new test method. Near-duplicate methods that differ only by literal
     input/expected-output data are fine to leave as-is for now — `tdd-refactorer` consolidates
     those into a parameterized test the next time it gets a refactor turn (see below);
     `tdd-tester` doesn't need to spot or convert them itself mid-loop.
3. Happy path before edge cases: cover the nominal/typical case first, then expand into
   boundary, invalid-input, and error-handling cases. (Deliberately the opposite of
   edge-case-first: it gives `tdd-implementer` a concrete case to generalize from on each
   turn, is more mechanical for an agent to execute without a risk-judgment call, and the
   interface-design risk that edge-case-first is meant to catch early is already addressed
   during Component Breakdown authoring.)

`tdd-tester` reports `done` once `code-change-expectations`' coverage checklist (branches,
error sources, boundary/invalid inputs, log output) is satisfied for the component.

**Structural red before behavioral red — only when it's actually needed.** Before adding an
`Assert`, `tdd-tester` writes the Arrange and Act for the targeted behavior and attempts to
build and run it with no `Assert` yet.
- If this doesn't complete cleanly — it fails to build (the target member doesn't exist), or
  it builds but throws/crashes when run (e.g. hitting unimplemented logic) — that's
  structural red either way: `tdd-tester` reports `structural-red: <TestName> — <reason>` and
  stops there for the turn. `tdd-implementer` resolves it with the smallest possible stub or
  fix — just enough for Arrange+Act to complete without throwing, returning an
  obviously-wrong value — reruns to confirm it now completes cleanly, and replies
  `structural-green: <TestName>`. Only then does `tdd-tester` add the `Assert`, producing
  genuine behavioral red.
- If Arrange/Act already completes cleanly — common when testing an existing,
  already-implemented member with different inputs, appending to an existing method, or
  adding a case to an already-parameterized test — `tdd-tester` adds the `Assert`
  immediately, in the same turn, and reports ordinary `red: <TestName> — <reason>`. No
  isolated structural turn when there was never a build/runtime-break risk.

This keeps "a red test must fail for the right reason" mechanically true either way: an
`Assert` is only ever added once Arrange/Act is already confirmed to complete cleanly —
whether that confirmation happened in this same turn, or a prior structural-green turn.

**The loop**, once a test method is past its structural stage (or skipped it):

1. Developer sends `tdd-tester` a turn: pick the next behavior per the rubric above, express
   it as one new `Assert`, run it, and reply `red: <TestName> — <reason>` or
   `done: <coverage summary>`. Full command output goes to a per-component log file, not the
   reply — the test name alone is enough to narrow the next verification run. The log file
   follows the existing `~/.dev-team/<repo-slug>/logs/` convention (per
   `_spec_AgentOrchestration.md`), named `<task-work-item-id>-tdd-<Component>.log`, appended
   to across every turn for that component.
2. If `done`, the loop ends for this component and it moves to Commits below.
3. Developer sends `tdd-implementer` a turn: make `<TestName>` pass — the dumbest change that
   satisfies only that assertion. Run the targeted test plus the rest of the component's
   suite to confirm no regression, and reply `green: <TestName>` or
   `escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope`.
4. If `green`, Developer gives `tdd-refactorer` one turn before continuing (see "Refactor,
   interleaved after every green" below) — it doesn't have to make a change every turn, but it
   gets the opportunity after every real green to steer the component toward well-designed
   code as it's being built, rather than deferring all cleanup to a single pass at the end.
5. Repeat from step 1.

**Escalation.** Autonomy is the goal — this pipeline has no mid-run human in the loop — so a
blocker resolves through increasingly decisive tiers rather than pausing:
- *Tier 1 — pair-internal:* before escalating, `tdd-implementer` may forward the blocker
  straight back to `tdd-tester` (the test hasn't gone green yet, so its Arrange/Act can still
  change) asking it to revise or explain. One retry.
- *Tier 2 — Developer resolves:* if that doesn't land, the blocked sub-agent sends Developer
  an `escalate` reply with a `recommended_action`:
  - `clarify` — Developer answers directly from the spec/task-brief context it already holds
    (expected to be the common case, since most ambiguity should already be resolved by
    Component Breakdown and the task brief) and relays the answer back into the loop.
  - `resolve_directly` — Developer follows the `implement-direct` skill to implement the
    disputed piece itself rather than mediating further, subsuming `tdd-implementer`'s turn:
    it runs the disputed test itself to confirm it now passes before handing control back.
    That behavior counts toward `tdd-tester`'s coverage exactly as if `tdd-implementer` had
    turned it green normally — the disputed test isn't discarded or rewritten, just made to
    pass by a different hand. This counts as a real green for refactor-turn purposes too:
    `tdd-refactorer` gets its usual turn (see "Refactor, interleaved after every green" below)
    before control returns to the pair for the next behavior.
  - `split_scope` — the behavior needs something outside this component's declared boundary
    (an unbuilt dependency, or a Component Breakdown gap). Developer reorders the remaining
    components or adjusts scope accordingly.
- *Tier 3 — best-effort, documented, non-blocking:* if Developer can't confidently resolve it
  either, it does not stall waiting on a person — it makes its best defensible call,
  implements accordingly, and records the ambiguity in its work summary as a known ambiguity
  (the same pattern `write-task-brief` already uses for open questions), for human review
  after the fact. Developer only returns an outright task failure when continuing would mean
  knowingly producing wrong code — feeding the pipeline's existing fixing/retry path.

**Refactor, interleaved after every green.** This is the "refactor" third of a genuine
red-green-refactor cycle: after every real green (an ordinary `tdd-implementer` `green` reply,
or a Tier 2 `resolve_directly` resolution) — never after a `structural-green`, since no real
behavior exists yet to clean up — Developer gives `tdd-refactorer` one turn to review the
component-so-far for duplication, brittle test setup, or a leftover naive/fake implementation
(e.g. a happy-path shortcut from an early `tdd-implementer` turn that a later edge case should
have generalized but didn't quite). `tdd-refactorer` doesn't have to make a change on every
turn — most turns may legitimately end in `no-refactor-needed` — but it gets the opportunity
after every green to steer the component toward well-designed code as it's being built, rather
than deferring all cleanup to a single pass at the end. Ground rules, adapted from the same
reference reviewed for this design:
- Read the surrounding block/function/module before changing anything.
- Preserve local naming and pattern consistency unless a new pattern is clearly better.
- Don't introduce an abstraction that conflicts with neighboring structure.
- Consolidate genuinely repeated test setup into a shared helper only when it clearly
  improves readability.
- Consolidate near-identical test methods — same Arrange/Act shape, differing only by
  input/expected-output literals — into a single parameterized/data-driven test. This is the
  canonical example of a behavior-preserving refactor, and the main mechanism for cleaning up
  the near-duplicate methods `tdd-tester` was deliberately allowed to leave behind mid-loop.
- No behavior changes, ever — a behavior gap found here is a new red for `tdd-tester` to pick
  up on its next turn for this same component, not something `tdd-refactorer` fixes itself.

`tdd-refactorer` reruns the full component suite after any change to confirm nothing moved,
and replies `refactored: <summary>` or `no-refactor-needed`. It never runs against a component
with a failing test — only after a real green.

**Commits.** Developer commits each component individually, via the existing
`commit-changes` conventions, once its base implementation is done — Wrapper and
Orchestrator components included, not only Testable ones. Since `tdd-refactorer`'s turns are
now interleaved throughout the loop and staged the same way every other turn is (never
committed mid-loop — see "Staging between turns" in `implement-tdd`), there is a single real
commit per Testable component, made once `tdd-tester` reports `done`; it picks up every
tester/implementer turn plus every interleaved refactor turn staged along the way. This gives
a real rollback checkpoint and a readable audit trail per component; whether the final
PR/merge history stays that granular or gets squashed is governed entirely by whatever
convention the target repo already uses for that, unaffected by this feature.

Every sub-agent reply is exactly one line — no diffs, no explanations. Developer never reads
the full test or implementation code mid-loop; it reasons only about the one-line status
stream (and the per-component log file, only if it needs to dig in), keeping its own context
cost roughly constant per turn regardless of how many turns a component needs. Full detail is
always recoverable from the files on disk if a later step (self-review, work summary) needs
it.

_Consequences:_ Turn count scales with the number of distinct behaviors in a component, not
just the number of components — this is the "a lot of turns" case anticipated up front, and
the one-line contract plus log-file offload is what keeps it affordable. Three narrowly
constrained roles, rather than two agents that both touch tests and code, make each agent's
job mechanically checkable and keep a refactor pass from quietly reintroducing a behavior
change under cover of "cleanup." Escalation resolves almost entirely inside the pair or at
Developer; human involvement is a rare, non-blocking, after-the-fact review path, not a
runtime dependency. Parameterization living exclusively in `tdd-refactorer` also means
`tdd-tester` never needs a carve-out to the frozen-Arrange/Act rule for this case — adding a
parameterized case is either "add a case to an existing parameterized test" (no Arrange/Act
change) or deferred entirely to the refactor pass.

---

### TDD practice rules standardized in `tdd-practices`

_Context:_ The epic specifies concrete practices that must govern every test the
tdd-tester/tdd-implementer pair writes, not just the ping-pong structure itself.

_Decision:_ Fold these rules into the new `tdd-practices` skill (see "`test-driven-development`
retired; splits into `behavior-driven-development` and `tdd-practices`" below), superseding
`test-driven-development`'s old generic "write unit tests, confirm they fail" language, as
non-negotiable dev-team conventions, per [[project-dev-team-agents]] style guidance already
established for this plugin:

- **AAA structure** — every test is Arrange, Act, Assert, in that order.
- **Red must fail for the intended reason.** Enforced mechanically by the ping-pong
  protocol's structural-then-behavioral red sequence (see the protocol decision above): a
  build break is always resolved to a passing, assertion-free stub before any `Assert` is
  added, so once a test is asserting, its failure is always a genuine behavioral mismatch —
  never a compile error or typo in disguise.
- **Arrange and Act are frozen once a test's first Assert has gone green.** After that point,
  only additional `Assert` statements may be appended to that test method (for closely
  related follow-on behaviors of the same scenario, per `tdd-tester`'s behavior-selection
  rubric above). A genuinely different scenario is a new test method, never a rewritten
  Arrange/Act on an existing one.
- **Naming:** default to `<Component>_<Scenario>_<ExpectedResult>` whenever the target project has no
  project-specific test naming convention of its own. `developer-standards` — i.e. the
  target project's own `CONTRIBUTING.md` / `.editorconfig` — always takes precedence when
  it specifies one.
- **Logs are a testable concern, because they reveal code flow.** Asserting a log message is
  a way of confirming which branch actually executed, not an end in itself.
  `code-change-expectations`' coverage checklist gains a fourth item: where a component's
  logging differs by branch or condition, that differentiation is asserted like any other
  observable behavior. A log statement inside an otherwise-trivial (branch-free) member
  doesn't need its own test, for the same reason the member itself doesn't.

_Consequences:_ These rules are process/behavioral, not language-specific, so they apply
identically regardless of the target project's stack. Naming syntax defers to the target
project when one is documented; the process rules (AAA, red-for-the-right-reason, frozen
Arrange/Act) do not — they are fixed dev-team conventions per the user's explicit choice.

---

### Fallback when a spec has no Component Breakdown

_Context:_ Specs written before this change (or specs describing something with no
meaningful component structure — e.g. a documentation-only change) won't have a Component
Breakdown section.

_Decision:_ `write-task-brief` omits "Components in scope" when the spec has no Component
Breakdown section covering the task — unchanged from the original design. What changes is
what `implement-task` does when it finds no section (or an empty one): see "Work outside
classified components" below — it no longer falls back to a separate single-agent procedure;
the no-Component-Breakdown case and the "some exit-criteria work isn't component-shaped"
case are now the same mechanism.

_Consequences:_ No spec needs to be retrofitted before this feature can ship. Adoption is
incremental — new specs get a written Component Breakdown to classify against; old specs and
non-code specs still get the full taxonomy and the full `implement-tdd` loop for anything
that turns out to carry logic risk, just classified by Developer on the spot instead of
read from a table.

---

### Work outside classified components: ad hoc triage, non-component work, and the final commit

_Context:_ Two related gaps surfaced during ADR-303's implementation and its human review.
First, a spec with no Component Breakdown at all gives `implement-task` nothing to dispatch —
the original design fell back to `test-driven-development`'s old "write unit tests, then
implement, one component at a time" procedure for this case, which is exactly the procedure
the ping-pong protocol (ADR-301/302) was built to replace, so reusing it here would leave two
competing TDD procedures for agents to choose between. Second, even a task with a full
Components in scope list can have real, in-scope work that isn't itself "a component" —
wiring/glue code, one-off scripts, moving files, writing documentation, running a dry run and
recording its output — work required to satisfy the exit criteria that was never going to
appear as a row in a Component Breakdown table, classified or not. Neither case had a defined
implementation procedure or commit path.

_Decision:_ `implement-task` never treats "no components to dispatch" (whether the list is
empty, or the spec has no Component Breakdown section at all) as "skip TDD, implement
free-form." Instead, after dispatching every classified component (unchanged from the
existing design), Developer triages whatever remains against the task's exit criteria into
two kinds:

- **Work that carries component-shaped logic risk, just not pre-classified** — something
  that would have earned a Wrapper/Testable/Orchestrator row had it been called out in a
  Component Breakdown, but wasn't (an uncaptured piece of a task that does have components,
  or *anything* in a task/spec with no Component Breakdown at all — the no-taxonomy fallback
  collapses into this same bucket). Developer classifies it itself, on the spot, invoking the
  new `component-taxonomy` skill (see below) for the same Wrapper/Testable/Orchestrator
  definitions a spec author uses, then routes it through `implement-direct` or `implement-tdd`
  exactly like a declared component. This is what actually retires the old batch procedure
  everywhere: there is no longer a code path in `implement-task` that reaches "write all the
  unit tests, then make them pass."
- **Work that was never component-shaped at all** — glue/wiring trivial enough to not need
  its own classification, one-off scripts, moving or renaming files, writing documentation,
  executing a dry run, and anything else unanticipated that doesn't fit the Wrapper/Testable/
  Orchestrator taxonomy — this list is illustrative, not exhaustive; Developer isn't expected
  to match against it, only to recognize when something isn't component-shaped. Developer just
  does this work directly, the same way it always has — no taxonomy, no TDD loop, no dedicated
  per-item commit. This generalizes the treatment the spec already gives whole tasks with no
  components (e.g. template scaffolding, see "Components in scope can legitimately be empty"
  above) from "the whole task" to "whatever part of the task isn't component-shaped."

Once every classified component is dispatched and both triage buckets are handled,
`implement-task` re-runs the E2E scenario suite (unchanged), then self-reviews (see the next
decision for its new position relative to the commit), then makes **one final commit**
covering: any non-component-shaped work from the second bucket, plus any fix the self-review
step required. Component-shaped work (classified or ad hoc) keeps its own existing
per-component commit from `implement-direct`/`implement-tdd` — the final commit never
re-touches those. If there's nothing left to commit (every exit criterion was satisfied by
classified components, and self-review found nothing), this step is skipped.

This means a "no Component Breakdown at all" task can now produce *multiple* commits (one
per ad hoc component Developer identifies, plus the final commit) instead of today's single
whole-task commit — a deliberate, desirable change in granularity, not an incidental one: it
matches the per-component audit trail every other task already gets, rather than preserving
"one commit" as a special case for these specs.

_Consequences:_ `test-driven-development`'s old per-component procedure (step 2: write unit
tests, then implement, one component at a time) is no longer reachable from any path in
`implement-task` and is removed outright — see "`test-driven-development` retired; splits into
`behavior-driven-development` and `tdd-practices`" below. Whether a spec "has a Component
Breakdown" stops
being a fork in *procedure* — it only changes whether Developer classifies work against a
written table or does the same classification from scratch. `plan-task`/`write-task-brief`'s
existing behavior (omit "Components in scope" when there's no Component Breakdown; list it as
explicitly empty when the task doesn't touch components) is unaffected — this decision only
changes how `implement-task` interprets those outcomes, not how they're produced.

The Wrapper/Testable/Orchestrator definitions themselves move out of this spec's prose and
into a new `plugins/dev-team/skills/component-taxonomy/SKILL.md`, since both spec authoring
and Developer's ad hoc triage now need the identical definitions and letting them diverge in
two places would be worse than the extra file. `spec-first-draft` invokes it while authoring
the Component Breakdown; `implement-task` invokes it only from the triage branch above — a
task brief with every component already classified never loads it, so the common case (spec
already fully classified) pays no extra cost.

---

### Self-review runs before the commit it can still affect

_Context:_ `implement-task`'s steps were originally ordered commit-then-review (Commit, then
Self-review) on the no-component fallback path, and per-component commits already happen
before the task-level self-review even on the dispatch path. If self-review finds something
that needs fixing, there was no defined step that commits the fix — it was only implied.

_Decision:_ `implement-task`'s ordering becomes: dispatch/triage (implement everything) → E2E
scenarios re-run → self-review → fix anything self-review requires → the one final commit
described in the previous decision. Self-review always runs against the full cumulative diff
(every per-component commit made so far, plus whatever non-component work is staged but not
yet committed) before that last commit closes the task out, so a review-driven fix is never
left implicitly uncommitted.

_Consequences:_ Per-component commits (Wrapper/Orchestrator/Testable) still land as soon as
each component goes green, unchanged — only the task-level wrap-up (leftover work plus
self-review) moves to the end, after review, instead of before it.

---

### `test-driven-development` retired; splits into `behavior-driven-development` and `tdd-practices`

_Context:_ With the two decisions above, no code path in `implement-task` reaches
`test-driven-development`'s old step 2 (write unit tests, then implement, one component at a
time) anymore — every unit-test-worthy piece of work, classified or ad hoc, now goes through
`implement-tdd`'s ping-pong loop instead. Leaving step 2 in place as dead prose invites an
agent to rediscover and use it, exactly the "two competing procedures" risk this
reconciliation closes. Beyond that, `test-driven-development` was already doing two unrelated
jobs under one name: the E2E-first/E2E-confirm wrapper around the whole task, and a set of
practice rules every TDD participant follows. Inspection of every other file that already
references this skill (`tdd-tester.md`, `tdd-implementer.md`, `tdd-refactorer.md`,
`tdd-red-turn`, `tdd-green-turn`, `tdd-refactor-turn`) confirms the split is already latent in
how the skill is used today — every one of those cites it only for "the Practice rules," never
for the E2E wrapper; only `implement-task`, `implement-direct`, and `implement-tdd` cite the
E2E-wrapper half.

_Decision:_ Retire `test-driven-development` entirely and replace it with two new skills, each
taking one of its former jobs:

- **`behavior-driven-development`** — the task-level E2E wrapper: write Gherkin E2E/API
  scenarios first (former step 1), confirm they all pass once everything is implemented
  (former step 3). `implement-task`'s dispatcher calls this by name before dispatch and again
  after everything is implemented. The name reflects what this step already is — writing
  Given/When/Then scenarios before any implementation exists — not a rebrand of the whole
  feature.
- **`tdd-practices`** — the Practice rules section (AAA structure,
  red-must-fail-for-the-right-reason, frozen-Arrange/Act after first green, naming
  convention, logging-as-a-testable-concern), unchanged in content. `tdd-tester`,
  `tdd-implementer`, `tdd-refactorer`, and their turn-skills (`tdd-red-turn`, `tdd-green-turn`,
  `tdd-refactor-turn`) all reference this by name instead of `test-driven-development`, which
  matches what they were actually citing it for all along.

Old step 2 (write unit tests, then implement, one component at a time) is dropped outright —
it isn't carried into either new skill. Every reference site enumerated above is updated to
point at whichever of the two new skills matches what it was actually using;
`implement-direct` and `implement-tdd` are the only files that need to cite both.
`code-change-expectations`'s generic pointer ("Use the `test-driven-development` skill when
implementing new code...") is updated to point at `implement-task`'s dispatcher instead, since
that instruction described exactly the retired step-2 procedure, not either new skill.

_Consequences:_ No file in the plugin references `test-driven-development` once both this
retirement task and ADR-303's rework ship — a clean retirement, not a deprecated alias kept
around for transition, but split across two tasks because not everything referencing
`test-driven-development` is merged yet. This task's own sweep is scoped to the eight
already-merged files enumerated above (`tdd-tester.md`, `tdd-implementer.md`,
`tdd-refactorer.md`, `tdd-red-turn`, `tdd-green-turn`, `tdd-refactor-turn`,
`code-change-expectations`, `implement-tdd`), plus updating `spec-first-draft` to invoke
`component-taxonomy` instead of restating its definitions inline. `implement-task` and
`implement-direct` are deliberately excluded from this sweep — both belong to ADR-303's still-
open PR #54, not yet merged, so ADR-303's own rework writes the correct
`component-taxonomy`/`behavior-driven-development`/`tdd-practices` references directly instead
of this task sweeping them in afterward (see the new task's description in `## Tasks` and
ADR-303's updated "Depends on" line).

## Planned Implementation

### Interfaces

**Component Breakdown table** (spec section, markdown table) — columns: Component, Type
(`Wrapper | Testable | Orchestrator`), Responsibility, Depends on.

**Components in scope** (task brief section) — components relevant to one task, listed in
dependency order as shown above.

**Ping-pong turn messages** (Developer → `tdd-tester` / `tdd-implementer` / `tdd-refactorer`,
via `SendMessage`):

The first turn to each newly spawned sub-agent (via `Agent`) includes the task brief and
spec file paths, plus that component's own Component Breakdown row (name, tier,
responsibility, dependencies) inline — enough to start without a round-trip. The sub-agent's
own `Read`/`Glob`/`Grep` tools cover anything beyond that (e.g. reading a dependency's actual
interface once it exists on disk); Developer's later turn messages stay one line and don't
re-summarize context already given on the first turn.

- To `tdd-tester` (structural): `"write Arrange and Act only for the next uncovered behavior of <Component> — no Assert yet."`
- To `tdd-implementer` (structural): `"resolve the build break for <TestName> with the smallest possible stub."`
- To `tdd-tester` (behavioral): `"add the first Assert to <TestName>, or pick the next behavior per the selection rubric, or reply 'done' if coverage is complete. Dependencies' interfaces: <summary>."`
- To `tdd-implementer` (behavioral): `"make <TestName> pass with the smallest change that satisfies only that assertion."`
- To `tdd-refactorer`: `"review <Component> for duplication, brittle setup, or naive implementations left over from green turns. No behavior changes."`

**Ping-pong turn replies** (one line each):
- `tdd-tester`: `structural-red: <TestName> — <reason>` | `red: <TestName> — <reason>` |
  `done: <coverage summary>`
- `tdd-implementer`: `structural-green: <TestName>` | `green: <TestName>` |
  `escalate: <reason> — recommended_action: clarify|resolve_directly|split_scope`
- `tdd-refactorer`: `refactored: <summary>` | `no-refactor-needed`

### Key Classes / Files

- [`plugins/dev-team/skills/spec-first-draft/SKILL.md`](plugins/dev-team/skills/spec-first-draft/SKILL.md)
  — add a Component Breakdown authoring step and template section (step 2, alongside
  Planned Implementation), invoking the new `component-taxonomy` skill for the tier
  definitions instead of restating them
- `plugins/dev-team/skills/component-taxonomy/SKILL.md` (new) — the Wrapper/Testable/
  Orchestrator definitions and property-level Wrapper carve-out, extracted from this spec's
  "Component taxonomy" decision into their own skill so `spec-first-draft` and
  `implement-task`'s ad hoc triage step (see below) invoke the identical text instead of two
  copies drifting apart. No agent invokes it unconditionally — `implement-task` only reaches
  it on the triage branch, so a task brief with every component already classified never
  loads it
- [`plugins/dev-team/skills/spec-readiness-review`](plugins/dev-team/skills/spec-readiness-review/SKILL.md)
  / [`researcher-spec-review`](plugins/dev-team/skills/researcher-spec-review/SKILL.md) —
  treat a missing/insufficient Component Breakdown as a blocking gap (per the concrete
  definition above) when the spec describes Testable-tier logic
- [`plugins/dev-team/skills/plan-task/SKILL.md`](plugins/dev-team/skills/plan-task/SKILL.md)
  and [`write-task-brief/SKILL.md`](plugins/dev-team/skills/write-task-brief/SKILL.md) — add
  the "Components in scope" section and its dependency-order computation
- `plugins/dev-team/skills/test-driven-development/SKILL.md` — deleted outright. Its E2E-first /
  E2E-confirm steps move to the new `skills/behavior-driven-development/SKILL.md` (renumbered
  1–2); its Practice rules section (AAA / red-for-the-right-reason / frozen-Arrange-Act /
  naming) moves to the new `skills/tdd-practices/SKILL.md`; its old step 2 (write unit tests,
  then implement, one component at a time) is dropped outright, carried into neither — per
  "`test-driven-development` retired; splits into `behavior-driven-development` and
  `tdd-practices`" above. No longer a fallback implementation path in its own right — see the
  next bullet
- [`plugins/dev-team/skills/code-change-expectations/SKILL.md`](plugins/dev-team/skills/code-change-expectations/SKILL.md)
  — add logging to the coverage checklist; its generic "use `test-driven-development`" pointer
  is updated to point at `implement-task`'s dispatcher instead, per the retirement decision
  above
- [`plugins/dev-team/skills/implement-task/SKILL.md`](plugins/dev-team/skills/implement-task/SKILL.md)
  — rewritten as the dispatcher: no interface change (still one `spawn_agent` step from the
  pipeline's perspective). For each component in the task brief's Components in scope list, in
  order, invokes `implement-direct` or `implement-tdd` per its tier. Then triages whatever
  exit-criteria work remains: anything component-shaped but uncaptured (or everything, when
  the spec has no Component Breakdown at all) is classified on the spot — invoking
  `component-taxonomy` for the tier definitions — and routed through
  `implement-direct`/`implement-tdd` the same as a declared component; anything
  non-component-shaped (glue code, scripts, file moves, docs, dry runs) is just implemented
  directly. Re-runs E2E scenarios, self-reviews, fixes anything the review surfaces, then makes
  one final commit for the non-component work plus review fixups (skipped if there's nothing
  left to commit) — see "Work outside classified components" and "Self-review runs before the
  commit" above
- `plugins/dev-team/skills/implement-direct/SKILL.md` (new) — single-shot direct
  implementation for one Wrapper or Orchestrator component (no test for Wrapper, one
  integration test for Orchestrator), plus `commit-changes`. Its build/test step states
  explicitly to fix any build errors or test failures before proceeding to commit, matching
  `code-change-expectations`'s existing explicitness. Also invoked by `implement-tdd` for a
  `resolve_directly` Tier 2 escalation, and by `implement-task`'s own triage for an ad hoc
  Wrapper/Orchestrator-tier piece of leftover work. For a Wrapper component, self-review treats
  "no test for this component" as expected, per its Component Breakdown tier (or ad hoc
  classification) — not a gap to flag, the way `code-change-expectations`' generic "missing
  test coverage" check would otherwise read it.
- `plugins/dev-team/skills/implement-tdd/SKILL.md` (new) — drives the full ping-pong +
  refactor choreography for one Testable component: spawns `tdd-tester`/`tdd-implementer`/
  `tdd-refactorer` together up front, runs the structural-then-behavioral red/green loop,
  giving `tdd-refactorer` one turn after every real green (never after `structural-green`),
  until `tdd-tester` reports `done`, then a single `commit-changes` picking up everything
  staged along the way (test turns, implementation turns, and every interleaved refactor
  turn)
- [`plugins/dev-team/agents/developer.md`](plugins/dev-team/agents/developer.md) — role
  section updated: orchestrates the tdd-tester/tdd-implementer/tdd-refactorer trio for Testable components; implements
  Wrapper/Orchestrator components directly; unaffected in every other respect (still owns
  branch setup, commit, self-review, work summary). Developer's existing `Task` tool entry
  (its current name for agent-spawning in this file) is the same capability this spec calls
  `Agent` elsewhere — no new grant needed there, just consistent naming. `SendMessage` (to
  resume a specific sub-agent's turn by its `agentId` — see the ping-pong protocol decision
  above) is the one genuinely new tool grant, since nothing in this repo currently resumes a
  spawned sub-agent turn by turn. The three new agent files don't need `Task`/`Agent` or
  `SendMessage` themselves, since none of them spawns or resumes further sub-agents.
  Incidental cleanup while in this file: fix stale skill-name references (e.g.
  `developer-implement` → `implement-task`) and rename the `Task` tool entry to `Agent` for
  consistency with current naming — drift unrelated to this feature, bundled in since the
  file is already being touched.
- [`plugins/dev-team/agents/researcher.md`](plugins/dev-team/agents/researcher.md) — role
  section updated: aware of component tiers and dependencies when producing task briefs (via
  `plan-task` / `write-task-brief`). Same incidental cleanup: fix stale skill-name references
  (e.g. `researcher-plan` → `plan-task`).
- `plugins/dev-team/agents/tdd-tester.md` / `plugins/dev-team/agents/tdd-implementer.md` /
  `plugins/dev-team/agents/tdd-refactorer.md` (new) — each is a thin, constraint-first agent
  file (Role / file-scope-or-behavior constraint / Ground or Practice rules / Skills), not a
  monolith with the ping-pong protocol's turn mechanics embedded directly in it. Each invokes
  its own turn-mechanics skill every turn to decide what to do, so Developer's messages to it
  stay generic and it never needs to be told whether the incoming turn is structural,
  behavioral, or (for `tdd-refactorer`) whether there's anything to clean up:
  - `tdd-tester.md` — tools: `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`, `Skill`.
    Constraint-first definition: only ever edits test files, never production files; adds
    exactly one new behavior per turn (one Assert, new method only when Arrange/Act genuinely
    differs); never spawns further sub-agents. Judges coverage completeness against
    `code-change-expectations`' checklist. Invokes `plugins/dev-team/skills/tdd-red-turn/SKILL.md`
    (new) every turn for the behavior-selection rubric, the structural-vs-behavioral decision,
    and the exact one-line reply format.
  - `tdd-implementer.md` — tools: `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`, `Skill`.
    Constraint-first definition: only ever edits production files, never test files; makes the
    smallest change — the "dumbest thing that could possibly work" — that satisfies the
    current turn's single assertion, never a generalized solution; never spawns further
    sub-agents. Invokes `plugins/dev-team/skills/tdd-green-turn/SKILL.md` (new) every turn for
    resolving a structural vs. behavioral turn, the Tier 1/2 escalation tiers, and the exact
    one-line reply format.
  - `tdd-refactorer.md` — tools: `Read`, `Glob`, `Grep`, `Edit`, `Write`, `Bash`, `Skill`.
    Constraint-first definition: only ever makes behavior-preserving changes to test or
    production files, after every real green (never after `structural-green`, never against a
    failing component); any behavior gap it notices is reported back as a new red for
    `tdd-tester`, never fixed in place. No escalation tiers, unlike the other two. Invokes
    `plugins/dev-team/skills/tdd-refactor-turn/SKILL.md` (new) every turn for the
    review-and-cleanup mechanics and the exact one-line reply format.
- [`plugins/dev-team/.claude-plugin/plugin.json`](plugins/dev-team/.claude-plugin/plugin.json)
  — version bump, per existing convention for skill/agent changes

### Data Flow

```
spec-first-draft
  │  writes ## Component Breakdown (Name, Type, Responsibility, Depends on)
  ▼
spec-task-breakdown
  │  tasks reference the components they touch (no format change needed —
  │  task descriptions already name affected files/areas)
  ▼
plan-task → write-task-brief
  │  filters Component Breakdown to this task's components,
  │  computes the dependency-ordered component list
  │  writes ## Components in scope to the task brief
  ▼
implement-task (Developer agent, dispatcher)
  │
  │  for each declared component, in dependency order:
  │      Wrapper / Orchestrator → implement-direct:
  │        Developer implements directly (no test for Wrapper, one
  │        integration test for Orchestrator), commit-changes
  │      Testable → implement-tdd:
  │        Developer spawns tdd-tester + tdd-implementer + tdd-refactorer
  │        together, drives structural-then-behavioral red/green ping-pong,
  │        giving tdd-refactorer one turn after every real green, until
  │        tdd-tester reports "done", then a single commit-changes
  │
  │  triage whatever exit-criteria work remains (declared components' list
  │  was empty, spec had no Component Breakdown, or some work just wasn't
  │  component-shaped):
  │      component-shaped but uncaptured → classify on the spot (Wrapper /
  │        Testable / Orchestrator) → same implement-direct / implement-tdd
  │        path as above, own commit
  │      not component-shaped (glue, scripts, file moves, docs, dry runs)
  │        → Developer implements directly, no TDD loop, no dedicated commit
  │        yet — staged for the final commit below
  │
  ▼
E2E scenarios re-run (behavior-driven-development's E2E wrapper step, unchanged)
  ▼
self-review → fix anything self-review requires
  ▼
final commit (non-component work + review fixups; skipped if nothing remains)
  ▼
work summary (including any Tier 3 known ambiguities)
```

## Related Features

| Feature | Scope |
|------|-------|
| [ADR-305](https://jodasoft.atlassian.net/browse/ADR-305) — Eval framework for dev-team skills/agents | Automated, repeatable verification for this repo's own skill/agent prose (synthetic fixtures, a scoring/judging mechanism, sandboxed agent runs) to replace the manual dry-run exit criteria this spec's tasks currently rely on. Out of scope for ADR-288 — this epic's task sizing assumes dry-runs; a follow-on spec could retarget these tasks' exit criteria at real evals once that framework exists. |

## Open Questions

None currently identified — the harness-gap interaction with `missing-test-harness` is
resolved above.

## Related Docs

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — this repo's own AAA / naming conventions, used as
  the default naming convention's precedent
- [`_spec_AgentOrchestration.md`](_spec_AgentOrchestration.md) — the pipeline architecture
  (`dev_team.py`, `workflow-orchestrate`, one-line agent return contracts) this feature
  builds on without modifying
- [`plugins/dev-team/skills/missing-test-harness/SKILL.md`](plugins/dev-team/skills/missing-test-harness/SKILL.md)
  — implementation-time rule this feature's design-time harness-scoping decision builds on
- [`plugins/dev-team/skills/test-driven-development/SKILL.md`](plugins/dev-team/skills/test-driven-development/SKILL.md)
  — current (pre-change) TDD flow
- [`plugins/dev-team/skills/code-change-expectations/SKILL.md`](plugins/dev-team/skills/code-change-expectations/SKILL.md)
  — current coverage checklist
- [`plugins/dev-team/agents/developer.md`](plugins/dev-team/agents/developer.md) — current
  developer agent definition

## Tasks

All tasks below are agent tasks (skill/agent prose changes in this repo, not target-project
code or infrastructure) — no human-required setup tasks are needed for this feature. Since
this repo's own "product" is agent-skill prose rather than compiled code, "testable" here means
a concrete dry run: exercising the changed skill/agent against a small synthetic example (or,
where noted, a real spec such as ADR-191, which will be restarted under this new process) and
confirming the described behavior actually occurs. Developer runs each dry run and includes its
output in the task's work summary; Reviewer judges the result against the task's exit criteria
as part of normal PR review — the same mechanism that already reviews code changes, with no new
tooling required. This is a stand-in for automated verification until
[ADR-305](https://jodasoft.atlassian.net/browse/ADR-305)'s eval framework exists.
When creating a PR, developer should note the results of dry runs in the PR description.

### [ADR-297](https://jodasoft.atlassian.net/browse/ADR-297) — Component Breakdown section in `spec-first-draft`

Add the `## Component Breakdown` table format and isolation-pattern authoring guidance
(dependency injection, State Object, sync-first, dependency-first-build) to
`spec-first-draft/SKILL.md`.

- [ ] `spec-first-draft/SKILL.md` documents the Component Breakdown table format (Component,
      Type, Responsibility, Depends on) and the four isolation-pattern guidance bullets
- [ ] Dry run: drafting a spec for a small synthetic feature (e.g. "cache a computed value with
      a TTL") produces a Component Breakdown table classifying each component as Wrapper,
      Testable, or Orchestrator, with correct `Depends on` edges
- [ ] The State Object pattern description covers both the default owner-mutates case and the
      ViewModel-style inverted-ownership exception

### [ADR-298](https://jodasoft.atlassian.net/browse/ADR-298) — Component Breakdown gap detection in spec readiness review

Teach `researcher-spec-review` (the check `spec-readiness-review` runs) to
treat a missing or insufficient Component Breakdown as a blocking gap. Depends on
[ADR-297](https://jodasoft.atlassian.net/browse/ADR-297).

- [ ] `researcher-spec-review` checks: every component the spec's prose describes appears in
      the table; every `Depends on` entry names a component that's actually in the table; every
      Testable component has an identified verification mechanism or a harness-building line
      item covering the gap (using the same existing-test-file-pattern search
      `missing-test-harness` already uses)
- [ ] Dry run: reviewing a synthetic spec with a component described in prose but missing from
      the table produces a blocking question; reviewing a synthetic spec with a dangling
      `Depends on` reference produces a blocking question; reviewing a synthetic spec with a
      Testable component and no verification mechanism or harness line item produces a blocking
      question
- [ ] Dry run: reviewing a complete synthetic spec (no gaps) produces no blocking questions for
      Component Breakdown

### [ADR-299](https://jodasoft.atlassian.net/browse/ADR-299) — Components in scope in task briefs, including zero-component and no-breakdown cases

Add the "Components in scope" section to `write-task-brief` (with `plan-task` computing the
dependency order), including the empty-list case (zero-component tasks like template
scaffolding) and the fallback when the spec has no Component Breakdown at all. Depends on
[ADR-297](https://jodasoft.atlassian.net/browse/ADR-297).

- [ ] `write-task-brief`/`plan-task` filters the spec's Component Breakdown to the task's
      components and lists them in topologically-sorted (dependency) order
- [ ] Dry run: a synthetic task brief for a task touching three components with a dependency
      chain produces a correctly ordered "Components in scope" list
- [ ] Dry run: a synthetic task brief for a template-scaffolding task produces an explicitly
      empty "Components in scope" list, not an omitted section
- [ ] Dry run: a synthetic task brief for a spec with no Component Breakdown section omits
      "Components in scope" entirely

### [ADR-300](https://jodasoft.atlassian.net/browse/ADR-300) — TDD practice rules and logging checklist item

Fold the AAA / red-for-the-right-reason / frozen-Arrange/Act / naming-convention rules into
`test-driven-development`, and add logging as a fourth coverage-checklist item in
`code-change-expectations`. Independent of the other tasks — no dependencies.

- [ ] `test-driven-development/SKILL.md` states AAA structure, the red-must-fail-for-the-right-
      reason rule, the frozen-Arrange/Act-after-first-green rule, and the default
      `<Component>_<Scenario>_<ExpectedResult>` naming convention (deferring to
      `developer-standards` when the target project documents its own)
- [ ] `code-change-expectations/SKILL.md`'s coverage checklist includes logging: where a
      component's logging differs by branch or condition, that differentiation must be
      asserted, unless the member is branch-free
- [ ] Dry run: reviewing a synthetic test file that renames Arrange/Act after its first Assert
      went green is flagged as a rule violation per the new checklist

### [ADR-301](https://jodasoft.atlassian.net/browse/ADR-301) — `tdd-tester` / `tdd-implementer` agents and the core `implement-tdd` red/green loop

Add the two new sub-agent definitions and the `implement-tdd` skill's structural-then-
behavioral red/green loop, including the behavior-selection rubric and all three escalation
tiers. Depends on [ADR-300](https://jodasoft.atlassian.net/browse/ADR-300) — `agents/tdd-tester.md`,
`agents/tdd-implementer.md`, and `implement-tdd/SKILL.md` reference `test-driven-development`'s
AAA / red-for-the-right-reason / frozen-Arrange-Act / naming rules by name rather than restating
them inline, so this is a real sequential dependency (ADR-300 must land first), not just an
informational note.

- [ ] `agents/tdd-tester.md` and `agents/tdd-implementer.md` exist, scoped to test-files-only /
      production-files-only respectively, with tools `Read`, `Glob`, `Grep`, `Edit`, `Write`,
      `Bash` only (no `Agent`/`SendMessage`), and reference `test-driven-development`'s practice
      rules by name rather than restating them
- [ ] `implement-tdd/SKILL.md` drives one Testable component through: structural red/green
      (only when Arrange/Act isn't already known-clean), behavioral red/green, the
      cheapest-structural-fit + happy-path-first behavior selection rubric, and all three
      escalation tiers (`clarify` / `resolve_directly` / `split_scope` / Tier-3 best-effort)
- [ ] Dry run: driving the loop against a small synthetic Testable component (e.g. a TTL cache
      lookup) from an empty test file to full coverage produces the expected sequence of
      one-line replies (`structural-red`/`structural-green`/`red`/`green`/`done`) and ends with
      every branch of the component covered
- [ ] Dry run: forcing a Tier 2 `resolve_directly` escalation confirms the disputed test ends up
      passing and is retained (not discarded) toward `tdd-tester`'s coverage count

### [ADR-302](https://jodasoft.atlassian.net/browse/ADR-302) — `tdd-refactorer` agent and the interleaved red-green-refactor pass

Add the `tdd-refactorer` agent and wire the refactor turn (including parameterized-test
consolidation) into `implement-tdd`, interleaved after every real green rather than as a single
pass at the end. Depends on [ADR-301](https://jodasoft.atlassian.net/browse/ADR-301).

- [ ] `agents/tdd-refactorer.md` exists, scoped to behavior-preserving changes only, same tool
      set as the other two tdd-agents
- [ ] `implement-tdd/SKILL.md` invokes `tdd-refactorer` for one turn after every real green in
      the component's loop (never after `structural-green`), and reruns the full component
      suite after each turn to confirm no behavior changed
- [ ] Dry run: running the refactor pass against a synthetic component left with two
      near-identical test methods (differing only by input/expected-output literals) produces a
      single consolidated parameterized test, with the full suite still green afterward
- [ ] Dry run: running the refactor pass against a component with no cleanup opportunity
      produces `no-refactor-needed` with no file changes

### [ADR-306](https://jodasoft.atlassian.net/browse/ADR-306) — Extract `component-taxonomy` skill; retire `test-driven-development` into `behavior-driven-development` and `tdd-practices`

Pull the Wrapper/Testable/Orchestrator definitions out into their own skill so
`spec-first-draft` and `implement-task`'s ad hoc triage share one copy instead of two; retire
`test-driven-development` entirely, splitting its E2E-first/E2E-confirm wrapper into
`behavior-driven-development` and its practice rules into `tdd-practices`; sweep every existing
reference to point at the right successor. Depends on
[ADR-297](https://jodasoft.atlassian.net/browse/ADR-297),
[ADR-300](https://jodasoft.atlassian.net/browse/ADR-300),
[ADR-301](https://jodasoft.atlassian.net/browse/ADR-301), and
[ADR-302](https://jodasoft.atlassian.net/browse/ADR-302) — all four are already merged and are
exactly the files this task edits. [ADR-303](https://jodasoft.atlassian.net/browse/ADR-303)
depends on this task in turn: it isn't merged yet, so its rework should reference
`component-taxonomy`/`behavior-driven-development`/`tdd-practices` directly rather than
`test-driven-development`, with no interim reference-sweep needed there.

- [ ] `plugins/dev-team/skills/component-taxonomy/SKILL.md` exists with the
      Wrapper/Testable/Orchestrator definitions and the property-level Wrapper carve-out,
      moved verbatim from this spec's "Component taxonomy" decision
- [ ] `plugins/dev-team/skills/behavior-driven-development/SKILL.md` exists with
      `test-driven-development`'s former step 1 (write E2E/API tests first) and step 3 (confirm
      E2E tests pass), renumbered 1–2
- [ ] `plugins/dev-team/skills/tdd-practices/SKILL.md` exists with
      `test-driven-development`'s former Practice rules section (AAA structure,
      red-must-fail-for-the-right-reason, frozen-Arrange/Act, naming convention, logging as a
      testable concern), unchanged in content
- [ ] `plugins/dev-team/skills/test-driven-development/SKILL.md` is deleted; every file this
      task touches (enumerated in this checklist) no longer references it by name.
      `implement-task/SKILL.md` and `implement-direct/SKILL.md` are the only remaining
      references in the plugin after this task ships — out of scope here since both belong to
      ADR-303's still-open PR #54; ADR-303's own rework resolves them
- [ ] `plugins/dev-team/skills/spec-first-draft/SKILL.md` invokes `component-taxonomy` for the
      tier definitions instead of restating them inline
- [ ] `agents/tdd-tester.md`, `agents/tdd-implementer.md`, `agents/tdd-refactorer.md`
      reference `tdd-practices` by name instead of `test-driven-development` (their only
      citation of it is the Practice rules one)
- [ ] `skills/tdd-red-turn/SKILL.md` and `skills/tdd-refactor-turn/SKILL.md` each have two
      distinct `test-driven-development` citations: their Practice rules citation is renamed to
      `tdd-practices`, and their separate "run build/test commands the same way
      `test-driven-development` / `code-change-expectations` document..." sentence drops the
      `test-driven-development` half entirely, citing `code-change-expectations` alone —
      consistent with the ping-pong protocol decision above, which already documents build/test
      command syntax as living solely in `code-change-expectations`
- [ ] `skills/tdd-green-turn/SKILL.md` has three `test-driven-development` citations, not two:
      the same build/test-command-syntax sentence as above (drop the `test-driven-development`
      half, `code-change-expectations` only), plus *two separate* Practice rules citations — an
      inline `## Practice rules` section reference and a distinct Skills-list entry — both
      renamed to `tdd-practices`
- [ ] `implement-tdd/SKILL.md` — already merged (ADR-301), not part of PR #54 — has four
      `test-driven-development` references: its "same build/test command syntax..." sentence
      drops the `test-driven-development` half, citing `code-change-expectations` alone (same
      treatment as the turn-skills above); its separate "that's reserved for the E2E re-run
      later in `test-driven-development`" mention is renamed to `behavior-driven-development`;
      its stale "Do NOT use this skill when the task brief
      has no Components in scope at all — fall back to `test-driven-development`'s single-agent
      flow" bullet is removed outright (not renamed) — that fallback path no longer exists under
      "Work outside classified components" above, since `implement-task`'s triage now handles
      the no-components case before `implement-tdd` is ever invoked; and its remaining single
      Skills-list bullet — which bundles both the practice-rules citation and the E2E-re-run-step
      citation into one line ("`test-driven-development` — practice rules the trio follows, and
      the E2E re-run step that...") — is split into two separate Skills-list entries, one citing
      `tdd-practices` and one citing `behavior-driven-development`
- [ ] `code-change-expectations/SKILL.md`'s pointer ("Use the `test-driven-development` skill
      when implementing new code...") is updated to point at `implement-task`'s dispatcher
      instead, since that instruction described the retired step-2 procedure
- [ ] Dry run: a spec author using `spec-first-draft` on a synthetic feature produces a
      Component Breakdown table using tier definitions read from `component-taxonomy`, not
      restated in `spec-first-draft` itself

### [ADR-303](https://jodasoft.atlassian.net/browse/ADR-303) — `implement-task` dispatcher and `implement-direct` skill

Rewrite `implement-task` as the per-component dispatcher, and add `implement-direct` for
Wrapper/Orchestrator components (and Tier 2 `resolve_directly` reuse). Depends on
[ADR-299](https://jodasoft.atlassian.net/browse/ADR-299),
[ADR-301](https://jodasoft.atlassian.net/browse/ADR-301),
[ADR-302](https://jodasoft.atlassian.net/browse/ADR-302), and
[ADR-306](https://jodasoft.atlassian.net/browse/ADR-306) (the `component-taxonomy` /
`behavior-driven-development` / `tdd-practices` extraction task above).

> **Review:** Revised below per PR #54's human review (changes requested) — the previous
> version of this task's exit criteria described the two-branch "no components / has
> components" fork now retired by "Work outside classified components" and "Self-review runs
> before the commit" above. PR #54 is still open (not merged), so this rework replaces its
> existing diff rather than tracking a separate delta.

- [ ] `implement-task/SKILL.md` iterates the task brief's Components in scope in order,
      invoking `implement-direct` for Wrapper/Orchestrator components and `implement-tdd` for
      Testable components, with no change to the skill's single-`spawn_agent` interface with
      the pipeline
- [ ] `implement-task/SKILL.md` triages any exit-criteria work left over after declared
      components are dispatched (including the entire task, when there's no Components in
      scope list at all) into: component-shaped-but-uncaptured, classified on the spot by
      invoking the `component-taxonomy` skill and routed through
      `implement-direct`/`implement-tdd`; and non-component-shaped work
      (glue/scripts/file moves/docs/dry runs), implemented directly with no TDD loop
- [ ] `implement-task/SKILL.md` re-runs E2E scenarios, then self-reviews, then fixes anything
      the review surfaces, then makes one final commit covering non-component work plus review
      fixups — skipped when there's nothing left to commit. Per-component commits are
      unaffected by this ordering change
- [ ] `implement-direct/SKILL.md` implements one component directly (no test for Wrapper, one
      integration test against real direct dependencies for Orchestrator), explicitly states
      to fix any build/test failures before proceeding, plus `commit-changes`
- [ ] Dry run: a synthetic task brief with one Wrapper, one Orchestrator, and one Testable
      component (in that dependency order) is fully implemented via the dispatcher, producing
      one commit per component and routing each to the correct skill — for the Testable
      component this is a full, real invocation of the `tdd-tester`/`tdd-implementer`/
      `tdd-refactorer` trio through their actual red/green/refactor loop (ADR-301/ADR-302's
      deliverables), not a stubbed pass-through, since this is the first end-to-end proof that
      the dispatcher and the ping-pong protocol actually compose
- [ ] Dry run: a synthetic task brief with zero components in scope, but exit criteria that
      require real logic, results in Developer classifying that work ad hoc and driving it
      through the same `implement-tdd`/`implement-direct` paths as a declared component — not
      through `test-driven-development`'s old procedure
- [ ] Dry run: a synthetic task brief with one declared component plus some
      non-component-shaped leftover work (e.g. a script and a doc update) produces the
      component's own commit, then one further final commit covering the leftover work
- [ ] Dry run: forcing a self-review finding on a synthetic task confirms the fix lands in the
      final commit, not left uncommitted

### [ADR-304](https://jodasoft.atlassian.net/browse/ADR-304) — Developer and Researcher agent role updates, plugin version bump

Update `agents/developer.md` (orchestrator role, `Task`→`Agent` rename, new `SendMessage`
grant, stale skill-name cleanup) and `agents/researcher.md` (component-aware task-planning
role, stale skill-name cleanup); bump `plugin.json`. Depends on
[ADR-303](https://jodasoft.atlassian.net/browse/ADR-303).

- [ ] `agents/developer.md` describes orchestrating the tdd-agent trio for Testable components,
      implementing Wrapper/Orchestrator components directly, and triaging any exit-criteria
      work left over after declared components are dispatched (per "Work outside classified
      components" above); its tool list includes `SendMessage` and renames `Task` to `Agent`;
      stale skill-name references are fixed
- [ ] `agents/researcher.md` describes component-aware task planning (tiers and dependency
      order) in `plan-task`/`write-task-brief`; stale skill-name references are fixed
- [ ] `plugins/dev-team/.claude-plugin/plugin.json` version is bumped
- [ ] Dry run: Developer, given a task brief with a mixed Wrapper/Testable/Orchestrator
      component list, completes the task end-to-end using only the tools now granted (no
      undocumented tool use)

### [ADR-305](https://jodasoft.atlassian.net/browse/ADR-305) — Create feature-work-item: Eval framework for dev-team skills/agents

Placeholder for the related, out-of-scope follow-up noted above — not a task in this epic, no
dependency on Tasks 1-8.

Scope: automated, repeatable verification for dev-team's own skills and agents, to replace the
manual dry-run exit criteria used throughout this spec.
