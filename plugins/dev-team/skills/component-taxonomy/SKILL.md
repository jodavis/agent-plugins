---
name: component-taxonomy
user-invocable: false
description: >
  Reference skill defining the Wrapper / Testable / Orchestrator component taxonomy used to
  decide how thoroughly a piece of code needs to be tested. Shared by spec-first-draft's
  Component Breakdown authoring and by Developer's ad hoc triage of work outside classified
  components.
---

Use this skill when:
- You are classifying a component (or a member within one) into a testing tier — while
  authoring a spec's Component Breakdown, or while triaging work that falls outside a task
  brief's already-classified components

## Component taxonomy

Every planned component is classified as exactly one of:

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
