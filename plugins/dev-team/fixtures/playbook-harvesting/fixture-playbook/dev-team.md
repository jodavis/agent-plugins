# dev-team overlay: stand-up-fixture-service

Optional annotations for dev-team consumption. Ignored by anyone reading `SKILL.md` and
`spec-template.md` directly; everything in `SKILL.md` degrades gracefully without this file.

## Component tier classifications

- Steps 1 and 2 (stamp, strip/replace) — Wrapper: mechanical, no branching judgment.
- Step 3 (validate configuration) — Testable: carries the schema-validation logic once the
  `validate-service-yaml` script referenced in Step 3's TODO is extracted.

## Step-to-pipeline-stage mapping

| Playbook step | Pipeline stage |
|---|---|
| 1. Stamp from the template | Researcher-authored task brief, executed by Developer |
| 2. Strip and replace | Developer |
| 3. Validate configuration | Developer, checked again at Reviewer sign-off |

## TDD hints

Step 3 becomes a genuine red/green candidate once the `validate-service-yaml` script exists:
write a failing test against a `service.yaml` missing a required field, then implement the
check.
