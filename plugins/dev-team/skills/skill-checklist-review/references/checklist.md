# Skill best-practices checklist

Two groups. Group A is mechanical — run `check_skill_structure.py` and relay its findings
verbatim. Group B needs a reader's judgment; evaluate each item against the actual SKILL.md and
reference-file contents, not against what the skill *should* say.

Every finding — either group — cites the file and, where it's a specific passage, a line number
or quoted fragment. "Feels off" is not a finding.

## Group A — structural (automated)

Covered by the script; do not re-derive these by reading:

- `name:` in frontmatter matches the skill's directory name.
- `description:` is present.
- Every file under `references/` is linked from `SKILL.md` at least once (no orphans).
- No reference file links to another local file (references are one hop from `SKILL.md`, not
  chained).
- Every local file path referenced from `SKILL.md` or a reference file actually exists.
- Every non-test script under `scripts/` has a corresponding test file.
- A soft grep for historical-record phrasing ("no longer", "used to", "previously", "removed
  the ... step") — surfaced as a prompt to check Group B's history-free item below, not an
  automatic fail.

## Group B — judgment (read and decide)

For each item: quote the passage (or note the absence), say whether it holds, and if not, what
the fix is.

1. **Description is terse and non-redundant with the name.** It should earn its tokens — not
   restate what "skill-checklist-review" already tells you, not pad with scope the name already
   implies.
2. **Internal-only skills read as internal-only.** A skill meant to be called by other skills,
   never directly by a user, has a minimal description — effectively "only use when instructed"
   — not a full user-facing pitch.
3. **No instruction the model already knows.** General programming/writing competence, common
   sense, or anything an agent would do by default doesn't need a line in the skill.
4. **History-free.** The skill describes what to do *now*. No "we no longer...", "previously
   this also...", "the X step was removed" — those belong in a changelog or commit message, not
   the skill. (If Group A's historical-phrasing grep fired, resolve each hit here.)
5. **Terse prose throughout, not just the description.** Fewer words for the same meaning,
   wherever a sentence can be cut without losing a decision, a constraint, or a scenario.
6. **Gotchas are present where the task plausibly has any.** Hard-won, non-obvious lessons
   (coordinate systems that don't line up, a flag required for headless mode, a gate that
   needs patching) are the highest-value content a skill can carry. Their absence in a skill
   whose task clearly involved friction is itself a finding.
7. **Degrees of freedom match the task.** High-freedom work (judgment calls, open design) is
   described by outcome, not forced into ordered steps. Medium-freedom work gives a template
   with explicit optional parts. Low-freedom, fragile, or exact-replay work is either a literal
   command block the agent must not vary, or a script — not prose the agent has to re-derive
   each time. Flag mismatches in either direction: prose where a script belongs, or a rigid
   script-like recipe imposed on genuinely open-ended work.
8. **Fragile or deterministic logic is scripted, not narrated.** Anything the model doesn't need
   to reason about — parsing, file-tree walks, exact multi-flag invocations — should be a script
   it runs, not steps it re-executes by hand each time.
9. **The skill checks its own output.** Where the task has a definable "done," the skill verifies
   against it (an exit-criteria list, a re-run test, a diff check) rather than declaring success
   unconditionally. Note whether it has a feedback loop, and whether it retries or escalates on
   a failed check.
10. **Script dependencies are self-installing, idempotently.** A script needing a runtime or
    package installs it as a step (and should no-op if already present) rather than assuming the
    environment has it — but don't flag an agent for skipping a redundant install it can already
    see is satisfied.
11. **Claims are verified, not copied.** Every command shown as something to run was actually
    run and produced the stated result — not paraphrased from a README or inferred from the
    source.
12. **One clear path, not a menu.** Prescriptive over exhaustive, unless the task is genuinely
    medium-freedom and the options are the point.
13. **Single responsibility and correct scope.** The skill covers one coherent job at the right
    unit boundary — it doesn't bundle unrelated capabilities, and it isn't a fragment of a job
    that needed a second skill to complete.
14. **Description actually triggers as intended.** Write 3–5 realistic user phrasings that
    *should* match and 2–3 near-miss phrasings from sibling/overlapping skills that *should not*.
    Compare each against the description's own wording — not vibes — and report any mismatch
    both directions (misses a real trigger, or fires on a near-miss).
