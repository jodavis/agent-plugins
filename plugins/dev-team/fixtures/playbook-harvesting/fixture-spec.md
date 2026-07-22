# Fixture: Stand Up Orders Service

> **Status:** Draft
> **Architecture doc:** `_doc_StandUpOrdersService.md` — authored by the final documentation task
> once implementation is complete; this spec persists afterward for harvesting
> **Feature-work-item:** FIX-100

This file is a **fixture** for the `harvest-playbook` dry run (see `RUN.md` in this
directory). It is never implemented — it exists only to be harvested, alongside
`exemplar-repo-1/`, `exemplar-repo-2/`, and `template-output/`. Do not treat this as a real
spec for this repository.

## Overview

Stand up a small "orders" microservice from the team's shared scaffold template
(`stand-up-fixture-service`), following the same construction order used for the sibling
`billing-service` instance (see `exemplar-repo-2/`).

## Responsibilities & Boundaries

- **Owns:** the orders service's HTTP handlers and its `service.yaml` configuration
- **Does not own:** the shared scaffold template itself, or the team's logging infrastructure
- **Integrates with:** the `stand-up-fixture-service` scaffold template

## Key Design Decisions

### Stamp from the template, then strip and replace

> [!NOTE]
> **Method:** We stamp every new service from the shared scaffold template first and commit
> that pristine output before touching anything else, so a later diff against the template
> always shows exactly what a given service customized.

_Decision:_ Run the scaffold template unmodified, commit the result, then strip the
placeholder tokens and replace them with the service's real name in a second commit.

### Validate configuration immediately after strip/replace

> [!NOTE]
> **Method:** We validate `service.yaml` against the schema right after the strip/replace
> commit, not later at deploy time — a placeholder token left behind by a rushed strip/replace
> pass on an earlier service wasn't caught until a failed deploy.

_Decision:_ Run the schema validator against `service.yaml` as the last construction step,
before any service-specific code is written.

## Planned Implementation

### Key Files

- `service.yaml` — service configuration (name, port, logging format)
- `README.md` — service-level readme stamped from the template
- `src/main.py` — service entry point

## Tasks

### Agent tasks

#### 1. Stand up the orders service

- [ ] `service.yaml`, `README.md`, and `src/main.py` exist, stamped from the
      `stand-up-fixture-service` template and stripped/replaced for `orders-service`
- [ ] `service.yaml` passes schema validation
