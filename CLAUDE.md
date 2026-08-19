# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

**Pre-implementation.** This repository currently contains only planning documents under
`docs/` (PDF format) — no application code exists yet. There is no `package.json`,
`pyproject.toml`, build system, or test suite to run. Before adding "commonly used commands"
to this file, the Phase 0 environment setup below needs to actually happen first.

The four planning docs are the source of truth and should be read in full before starting
implementation work — they are dense (40+ sections in the architecture doc) and this file
only summarizes the parts a coding agent needs to not violate on day one:

- `docs/PRD.pdf` — what is being built and why (product requirements)
- `docs/SOFTWARE ARCHITECTURE AND TECHNICAL DESIGN.pdf` — how it's built (system design,
  data model, module boundaries, ADRs) — this is the primary technical reference
- `docs/API SPEC.pdf` — endpoint-by-endpoint contract (`/api/v1/...`)
- `docs/IMPLEMENTATION PLAN.pdf` — phased build order with definition-of-done per phase

These are meant to eventually become `docs/PRD.md`, `docs/SOFTWARE_ARCHITECTURE_AND_TECHNICAL_DESIGN.md`,
`docs/API_SPEC.md`, `docs/IMPLEMENTATION_PLAN.md` — the PDFs are the only copies today.

## What Sijil is

Sijil is an AI-driven trade-compliance platform for UAE importers, exporters, freight
forwarders, and customs brokers, built by a solo technical founder. It ingests shipment
documents (commercial invoice, packing list, bill of lading / air waybill) and provides four
capabilities:

1. **HS code classification** — predicts the 12-digit UAE HS code per line item with a
   confidence score and GRI-based reasoning
2. **Cross-document consistency checking** — flags mismatches between invoice/packing-list/BOL
   that would trigger Dubai Customs (Mirsal 2) Yellow/Red-channel review
3. **Permit-applicability triage** — determines which of ~10 UAE regulators (MOCCAE, MOHAP,
   TDRA, ESMA/MoIAT, Ministry of Economy, etc.) require a permit for a shipment
4. **CEPA origin qualification** — determines preferential-tariff eligibility under a curated
   subset of UAE trade agreements

It is an **advisory tool at MVP** — the user still files with Mirsal 2 themselves; Sijil never
auto-files anything with a government system (see ADR-002 in the architecture doc).

## Planned architecture (from the architecture doc)

**Modular monolith**, not microservices — one deployable FastAPI backend with strict internal
module boundaries, chosen specifically because a solo founder can't operate a service mesh.

Stack: Python/FastAPI backend + Next.js frontend + PostgreSQL with `pgvector` (one database
for both relational data and vector search — no separate vector DB) + Redis/Celery for async
processing + S3-compatible object storage + an LLM provider (Claude) for document extraction
and HS classification reasoning.

### Planned repository layout

```
sijil/
├── backend/app/
│   ├── api/v1/          # FastAPI route handlers — thin controllers only
│   ├── services/        # Business logic — one file per domain service
│   ├── repositories/    # Data access — one file per aggregate
│   ├── models/          # SQLAlchemy ORM models
│   ├── schemas/         # Pydantic request/response schemas
│   ├── workers/         # Celery task definitions (parallel entry point to api/)
│   ├── integrations/    # External service clients (llm_client.py, ocr_client.py, ...)
│   ├── middleware/ config/ utils/
│   └── tests/{unit,integration,fixtures,golden_sets}/
├── frontend/            # Next.js app router
├── data/permit_rules/   # Versioned YAML/JSON permit rules — NOT a database table
└── docs/
```

### Dependency direction (enforced, not just convention)

`api/` → `services/` → `repositories/` → `models/`, plus `services/` → `integrations/`.
Each layer may only import from the layer(s) listed to its right:

- `api/` may import `services/` and `schemas/` only — never `repositories/` or `models/` directly
- `services/` may import `repositories/` and `integrations/` only — never `models/` directly
- `repositories/` may import `models/` only — never `services/` (would be circular)
- `workers/` is an alternate entry point parallel to `api/` — it calls `services/` directly

A CI lint rule (e.g. `import-linter`) is intended to enforce this mechanically once code
exists, specifically because solo-founder time pressure is called out as the likeliest way
these boundaries get violated.

### Five domain services + billing

`ClassificationService`, `ConsistencyService`, `PermitTriageService`, `CEPAOriginService`,
`ReportService`, plus `BillingService` — each is a thin, testable service behind the
`api/`/`workers/` entry points, backed by per-aggregate repositories.

### The one abstracted interface

Only `LLMClient` (a `Protocol`) is abstracted, so the LLM provider can be swapped without
touching `classification_service.py`. Everything else (repositories, other services) is
concrete — introducing interfaces for single-implementation classes is explicitly called out
as premature abstraction to avoid.

## Non-negotiable rules ("Do Not Do This" — architecture doc Section 36)

- Never put business logic in API route handlers — validate and delegate only
- Never call the database directly from a service — always go through a repository
- Never let classification silently return a low-confidence guess as if certain — always
  surface uncertainty (`requires_manual_review=True`, never a false-confident answer)
- Never hardcode permit/CEPA rules as scattered `if` statements — keep them in the versioned
  data files under `data/permit_rules/` so they're auditable without a code deploy
- Never default missing CEPA origin data to "does not qualify" — request the missing input
  instead; a false negative costs the user real money (this is enforced via an
  `"insufficient_data"` response value, not `false`)
- Never introduce microservices, Kubernetes, or a separate vector database without a measured
  performance reason — `pgvector` inside the existing Postgres instance is sufficient at the
  targeted scale (~500 companies / ~5,000 shipments/month)
- Never auto-file anything with a government system without explicit, logged user confirmation
- Never log raw document content, full JWT tokens, or raw LLM prompts containing sensitive
  commercial data
- Never treat a stale permit-rules or CEPA-rules table as a "fix later" code problem — it's a
  recurring compliance-data maintenance responsibility (quarterly review), not a one-time load

## Tenant isolation

Every shipment/document/report query must be scoped by `company_id` derived from the
authenticated user's JWT — never trust a client-supplied `company_id`. There is no
"query all shipments" repository method without a mandatory tenant-scope parameter, by
design. Broker access to a managed company is checked via an explicit `broker_company_id`
relationship, never inferred. This is the single most-tested guarantee expected in Phase 1
(a user from Company A must never be able to read Company B's data, even via a crafted
request).

## Testing expectations once code exists

- **Golden-set regression suite** (`tests/golden_sets/`) — a maintained set of 200+ verified
  product-description-to-HS-code pairs. This is called out as the single most important test
  suite in the system; CI should fail any merge that drops classification accuracy below the
  last known-good baseline. Build this suite in the same phase as `ClassificationService`
  (Phase 3), not later.
- Unit tests for every rules-engine function (permit triage, CEPA logic, consistency
  comparison) — these are pure functions.
- Integration tests against a real (containerized) test Postgres for repository flows.
- All external services (LLM, OCR, billing) are mocked in unit/integration tests; only
  E2E/staging tests hit real sandboxed APIs.

## Build order (implementation plan)

Phase 0 (env/tooling) → Phase 1 (auth, company/user model, upload+storage, tenant isolation) →
Phase 2 (OCR + LLM document extraction) → **Phase 3 (HS classification — the core
differentiator, validated first and given disproportionate iteration time)** → Phase 4
(consistency checking) → Phase 5 (permit triage — depends on Track A data) → Phase 6 (CEPA
origin — depends on Track B data, sequenced last as the most complex rules logic) → Phase 7
(reports, billing, polish) → Phase 8 (pilot onboarding).

Two non-engineering data tracks run in parallel from day one and are **not blocked by any
coding phase**: Track A (permit-rules research: HS-code-to-regulator mapping for MOCCAE,
MOHAP, TDRA, ESMA/MoIAT, Ministry of Economy) and Track B (CEPA rules-of-origin research,
starting with India/Indonesia as candidate priority agreements). These directly gate Phases
5 and 6 respectively.

## Key assumptions baked into the design (flagged in the docs, not settled facts)

- HS classification is advisory only, not a legally-binding service, until there's traction
  and legal/insurance coverage
- Permit and CEPA rules are a manually-maintained, versioned dataset — never live-scraped
  from government sites
- UAE/GCC-region hosting is preferred but not confirmed as a hard legal requirement
- Data retention target is 5 years (aligns with UAE VAT record-keeping), pending legal
  confirmation
