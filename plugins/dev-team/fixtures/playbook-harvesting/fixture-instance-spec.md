# inventory-service — Instance Spec

> **Playbook:** plugins/dev-team/fixtures/playbook-harvesting/fixture-playbook/

This file is a **fixture** for `spec-task-breakdown`'s playbook-seeding dry run (see `RUN.md`
in this directory). It represents the thin instance spec that `spec-first-draft`'s instance
mode would draft from `fixture-playbook/spec-template.md`. Do not treat this as a real spec
for this repository.

## Domain

Tracks warehouse stock levels and reserves inventory for pending orders.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | /inventory/{sku} | Look up current stock for a SKU |
| POST | /inventory/{sku}/reserve | Reserve units against a pending order |

## Applicable ADRs

- [ ] Not applicable — no existing ADRs govern inventory reservation semantics yet

## Deltas from playbook assumptions

- Logging format: JSON (matches the playbook default; no delta)
- Port: 8090 instead of the playbook's default 8080, to avoid a collision with the
  `orders-service` instance already running locally during integration testing
