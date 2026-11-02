---
name: skill-fix-proposal
user-invocable: false
description: >
  Use after skill-checklist-review has findings for a skill directory and the user wants to act
  on them. Drafts a concrete edit per finding, gets the user's approval on which to apply, applies
  those, and re-runs the review to confirm they actually resolved.
---

Takes one target skill directory (the same one `skill-checklist-review` was just run against) and
turns its findings into edits. Never edits anything without the user picking it in step 3 — this
skill drafts changes, it does not decide to make them.

## Steps

### 1 — Get the findings

If `skill-checklist-review` was already run against this target directory earlier in this
conversation, reuse those findings — don't redo the judgment pass from memory of what you
concluded; re-read the specific passages again when drafting each edit in step 2. Otherwise, run
`skill-checklist-review` against the target now.

### 2 — Draft one proposed edit per actionable finding

Skip only findings explicitly marked `no_change_needed` or a passing Group B item. For everything
else, draft a concrete before/after edit — not a description of what should change, the actual
replacement text — grouped by file:

- **Group A findings** generally have an unambiguous fix (add the missing `description:`, fix a
  dangling link's target, link an orphaned reference file in, write the missing test file). Draft
  it directly.
- **name-mismatch** has two valid fixes — rename the directory, or change the frontmatter `name:`
  to match it. Default to changing the frontmatter (lower blast radius: nothing else references
  the directory path) and say so, but note the alternative so the user can override in step 3.
- **Group B findings** need an editorial rewrite of the flagged passage. Keep the rewrite as
  close to the original as the fix allows — this is a correction, not a rewrite license.
- A finding with no confident fix (e.g. "gotchas are missing" with nothing in this conversation's
  research to draw one from) gets a proposal of "needs input from the skill's author" instead of
  an invented fix — don't fabricate a gotcha that was never actually hit.

### 3 — Get approval

Present every drafted edit as a diff (current → proposed) with the checklist item it resolves.
Use `AskUserQuestion` (multi-select) grouped by finding, defaulting to all Group A edits selected
and Group B edits unselected — Group A fixes are low-risk and mechanical; Group B rewrites touch
prose the skill's author may feel differently about.

**Gotcha — partial answer echo:** when `AskUserQuestion` is called with multiple questions, the
tool result may only explicitly restate the answer to whichever question got a custom/"Other"
response — a standard option pick on another question in the same batch can go unechoed. Don't
read silence as "accepted the recommended option"; if it's not explicitly confirmed, say what
you're assuming before acting on it.

### 4 — Apply approved edits

Apply each approved edit with `Edit`. If the chosen name-mismatch fix is a directory rename, use
`git mv` if the directory is tracked, plain `mv` if not, and update every reference to the old
directory name across the plugin (`grep -rl` for the old name under `plugins/`) — a rename that
leaves stale cross-skill links is worse than the mismatch it fixed.

### 5 — Re-verify

Re-run `skill-checklist-review`'s structural script against the target directory. Confirm every
applied Group A edit's finding is gone. For applied Group B edits, re-read the changed passage
against its checklist item and confirm it now holds.

### 6 — Report

List what was applied, what was proposed but declined, and what had no confident fix — each tied
to its checklist item. End with the new verdict (ready / still needs changes, and why).
