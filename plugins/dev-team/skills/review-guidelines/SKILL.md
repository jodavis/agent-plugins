---
name: review-guidelines
user-invocable: false
description: >
  Use when you are reviewing code changes.
  Defines the priority-ordered criteria for evaluating a diff.
---

Use this skill when:
- You are reviewing code changes

Evaluate the diff against each dimension below in priority order. For each issue you find, note the file, line number, and a clear description of the problem.

## Priority 1 — Correctness and fault tolerance

- Are all exception paths handled? No swallowed exceptions, no empty `catch` blocks (unless there is a comment with a good justification).
- Are `CancellationToken` parameters present in every async method signature? No default values — callers must pass explicitly.
- Are there blocking calls (`.Result`, `.Wait()`, `Thread.Sleep`) on async code paths?
- Does error handling propagate faithfully, or does it silently discard failures?

## Priority 2 — Security

- Is user input validated at system boundaries?
- Are there SQL injection, command injection, or path traversal risks?
- Is sensitive data (tokens, passwords, PII) logged or returned in error messages?
- Are authentication/authorization checks present where the architecture requires them?

## Priority 3 — Performance

- Are there N+1 query patterns (fetching inside a loop that could be batched)?
- Is there synchronous I/O on async code paths?
- Are there unnecessary allocations in hot loops (string concatenation, LINQ on every call)?
- Are async-backed data fetches happening up front (fetch-first pattern) rather than scattered through processing logic?

## Priority 4 — Documentation

- Does new code conform to the design described in the relevant architecture documentation?
- If the implementation changed the design (new interface, changed responsibility, new dependency), has the documentation been updated?
- Have new documentation files been added where necessary?

## Priority 5 — Code style (note, do not block)

- Do naming conventions follow `CONTRIBUTING.md` (`ClassName_Method_Scenario_ExpectedResult` for tests)?
- Do log messages use `[LoggerMessage]` source-generated methods?
- Do tests use `MockBehavior.Strict` and `Expect_*` helpers?
- Is there a `CreateSut()` method?

Post inline comments for all Priority 1–4 issues. Note Priority 5 issues in the overall summary only.
