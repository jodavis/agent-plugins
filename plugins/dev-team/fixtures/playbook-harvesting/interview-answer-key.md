# Fixture: Harvest Interview Answer Key

Scripted answers for the `harvest-playbook` dry run's interview step (see `RUN.md`). The
validating subagent role-plays the user strictly from this key — it never improvises an
answer beyond what is written here.

## Fallback rule

For any interview question not covered by the table below, answer exactly:

> no answer — proceed with your recommendation

## Scripted answers

| # | Question theme | Scripted answer |
|---|---|---|
| 1 | Playbook name | `stand-up-fixture-service` |
| 2 | Confirm Method marker candidate: stamp-then-strip/replace ordering | Yes — keep this as a construction step, with its rationale. |
| 3 | Confirm Method marker candidate: validate `service.yaml` right after strip/replace | Yes — keep this as a validation gate. |
| 4 | Exemplar conflict: `exemplar-repo-1` (orders-service) uses JSON logging in `service.yaml` at its final commit, `exemplar-repo-2` (billing-service) uses plain-text logging — which is canonical for the playbook? | JSON logging is canonical. Billing's plain-text logging predates the team's structured-logging standard and should be recorded as a manual exception, not the default step. |
| 5 | A drafted step references dev-team-specific vocabulary (e.g. naming an internal skill or agent by name) — how should it be phrased so a reader with no agent can follow it? | Rephrase it as a plain instruction: name the concrete command or file to check, never a skill or agent. |
| 6 | Shared-artifact candidate: the strip/replace logic is duplicated across services — extract it into a shared script now, or record it as a TODO? | Record it as a TODO with a manual fallback for now; there is no bandwidth to build the shared script yet. |
| 7 | Output directory for the playbook | Use the `--out` directory supplied on the command line as-is. |
