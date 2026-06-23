---
name: write-e2e-test
description: >
  Use when you are writing E2E tests.
  Establishes where to put feature files, how to write Gherkin scenarios, and how step definitions should be structured.
---

Use this skill when:
- You are writing E2E tests

## Location

Write new feature files in the headless E2E host:

```
test/AdaptiveRemote.EndToEndTests.Host.Headless/Features/
```

Follow all conventions in `test/_doc_EndToEndTests.md`.

## Scenario writing rules

**Use existing steps whenever possible.** Before writing a new step, search for matching step definitions:

```bash
grep -rl "Given\|When\|Then" test/ --include="*.cs" | head -20
```

**Write generalized step phrasing.** Each `Given`, `When`, and `Then` step must describe something a human could do or observe manually — not an internal implementation detail.

- Good: `When the user opens the settings panel`
- Bad: `When SettingsViewModel.OpenCommand is executed`

**One scenario per behaviour.** Keep scenarios focused. A scenario that covers multiple independent behaviours is harder to diagnose when it fails.

**Represent the correct behaviour.** For bug investigations, first write the scenario to observe the bad behaviour (it should pass), then modify it to assert the correct behaviour (it should now fail). This failing test is the investigation anchor.

## Step definition rules

Step definitions must delegate logic to test service methods — they should not contain application logic themselves. The step definition translates the human-readable step into a call to the appropriate service.
