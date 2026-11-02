---
name: skill-checklist-review
user-invocable: false
description: >
  Use when asked to review, audit, score, or sanity-check a skill (a SKILL.md and its supporting
  files) against best practices — not when writing or revising one. Runs a deterministic
  structure check, then a judgment pass against references/checklist.md, and reports findings.
---

`<skill-dir>` below is this skill's own base directory — the "Base directory for this skill" path
shown when invoked — resolve it to that literal path.

Evaluates **one target skill directory** (passed in as an argument, e.g. `<target-dir>` below)
against `references/checklist.md`. Read that checklist in full before step 2 — it defines every
check this skill runs and is the only place their exact wording lives.

## Steps

### 1 — Run the structural check

```bash
python3 "<skill-dir>/scripts/check_skill_structure.py" "<target-dir>"
```

This covers every Group A item in the checklist. Relay its findings as-is — don't re-derive them
by re-reading the files; the script is authoritative for everything it checks. If it exits
non-zero, at least one finding is `error` severity.

### 2 — Read the target skill in full

Read `<target-dir>/SKILL.md` and every file it links to (which, per Group A, should be every file
under `references/` and `scripts/` — the script already flagged any that weren't). If the target
is itself large or references a lot of material, read all of it anyway: a judgment pass that
skips content isn't a judgment pass.

### 3 — Run the judgment pass

Work through `references/checklist.md` Group B, item by item. For each: quote the passage (or
note its absence), state whether it holds, and if not, the fix. Do not skip an item because it
"seems fine" without pointing at the specific text that makes it fine.

For Group B item 14 (trigger check), actually write out the sample phrasings and compare them
against the description's wording before concluding — don't just assert it would trigger.

**Gotchas in the structural check's findings:** `check_skill_structure.py` deliberately only
treats `references/...`, `scripts/...`, `assets/...` paths, and bare `<name>/SKILL.md` cross-skill
links as "local" — anything else (`~/...`, `.dev-team/config.yaml`-style runtime paths, or a
deeper path to another tool's own SKILL.md file, e.g. an installed plugin's) is intentionally not
checked for existence, because those were confirmed false positives (runtime config that
legitimately doesn't exist yet, or another tool's bundled skill outside this repo) when this
checker was run against every skill in this plugin.
An unresolved `<name>/SKILL.md` link is reported as `warn`, not `error`, for the same reason — it
might be a deliberate external reference. Don't "fix" the checker to flag these again without
re-confirming they're not still false positives.

**Gotcha — case-insensitive mounts:** on a case-insensitive-but-case-preserving filesystem (e.g.
a macOS-host `virtiofs` bind mount, common in this kind of container), `Path.resolve()` echoes
back whatever case the *argument* used, not the true on-disk directory name — so a `name-mismatch`
finding can be entirely an artifact of how the target path was typed, not a real mismatch. The
checker already corrects for this (`_true_dirname()` scans the parent directory for the real
entry); if a `name-mismatch` still looks wrong, re-run `ls` on the parent directly before trusting
either the finding or the argument's casing.

### 4 — Report

Produce one report, organized as:

- **Verdict** — one line: ready, or needs changes.
- **Errors** — any `error`-severity Group A finding. These block "ready."
- **Warnings / info** — remaining Group A findings, each with the checklist item it maps to.
- **Judgment findings** — every Group B item, in order, with its verdict and evidence. Include
  passing items too, briefly — a silent checklist item isn't a verified one.

Every finding cites its evidence — a quoted passage, a file:line, or a named absence. No finding
rests on a vibe.
