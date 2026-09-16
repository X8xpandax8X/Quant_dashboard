# Supabase architecture and implementation plan

Date: 2026-09-16. **Implementation approved 2026-09-16; core work in progress.**

## Main decision

Make Supabase Postgres the canonical relational backend, Supabase Storage the remote
history store, and Supabase Auth with Google the identity authority. Data Engine,
Quant Engine and Portfolio Service remain separate, coordinated by FastAPI /api/v1.
Database row-level security is the final ownership boundary. Production AI remains
future-only. Next.js is still the frontend target, but core backend parity comes first.

This replaces the earlier SQLite/local-Parquet production storage and OAuth2 Proxy
identity design. The default demo/legacy adapters continue to run; the new opt-in core foundation awaits actual Supabase integration and cutover.
The subsequent “continue implementing” request authorizes core implementation. No hosted project is provisioned or migrated by this local checkpoint.

## Current code audit and preservation

| Current evidence | Gap against target | Incremental treatment |
|---|---|---|
| data_engine/service.py providers, normalization, provenance and stale fallback | Constructs disk-based CacheStore; freshness partly fixed; in-process locks | Preserve providers, inject remote repositories/object store/central policies and DB refresh leases |
| data_engine/cache.py SQLite + local immutable Parquet | Developer disk is authoritative | Supabase metadata + private versioned objects; no dual production truth |
| quant_engine/analytics.py pure NumPy/Pandas math | Improve explicit input/output types and coverage where missing | Preserve formulas and fixtures; enforce no I/O imports or dependencies |
| app/db.py owner-filtered SQLAlchemy SQLite, revision/idempotency | No database RLS; JSON target positions | Extract Portfolio Service, normalize targets, preserve atomic semantics under user-context RLS |
| app/auth.py signed demo cookie or proxy-secret/Google-subject hash | Not Supabase JWT identity; existing owner IDs are not Supabase UUIDs | Verified identity mapping and Supabase Auth cutover, no guessed owner remapping |
| app/api.py coordinates market/quant/private endpoints | Direct persistence setup and some domain logic in route module | Inject service interfaces, retain versioned response contracts |
| frontend/ and LPPLS/ | Framework migration and UI verification unfinished | Preserve both; minimum auth/API compatibility now, Next.js later |

This was a targeted source audit for planning, not a full new independent security audit.

## Execution after approval

| Phase | Deliverable | Exit evidence |
|---|---|---|
| A — audit and contracts | Verify canonical Git checkout; domain boundaries, schemas, identity/data migration inventory | Reviewed interfaces and no lost dashboard scope |
| B — Supabase foundation | Select development environment; Auth/admission, schema, grants, RLS, private Storage, migration tooling | Repeatable clean setup; actual A/B/unauthenticated/unadmitted isolation tests |
| C — Data Engine | Provider adapters, central freshness, remote metadata/Parquet, refresh leases and failure recovery | Missing/stale/throttled/duplicate data fixtures; concurrency and interrupted-publication tests |
| D — Quant Engine | Typed pure functions for all retained metrics and explicit edge cases | Known numerical fixtures; identical input/output; no DB/network/auth dependencies |
| E — Portfolio Service | Private CRUD, scenario weights, holdings/transaction boundaries, atomic revision/idempotency | Real RLS tests, parent-owner constraints, rollback/retry/expiry recovery |
| F — FastAPI integration | Versioned APIs coordinate all domains; minimum browser auth adaptation; deterministic CI | Contract/API/security tests and existing dashboard parity |
| G — AI placeholder | Document structured authorized analysis context and future evaluation gates | Core works with no LLM key, runtime or framework |

After core parity, migrate the preserved React UI to Next.js, complete responsive/
accessibility work and independent integrated audit. Do not introduce a simultaneous UI
redesign. Sequence packages by dependencies rather than cosmetically moving every file.

## Non-negotiable design choices

- User-scoped DB requests carry the validated user's JWT; a service key bypassing RLS
  cannot serve as the normal Portfolio Service connection.
- Keep explicit Google email admission, backed by protected active membership in the DB.
- Preserve target weights in basis points separately from real quantities/costs/trades.
  Do not manufacture a ledger from existing saved simulation weights.
- Private immutable Storage objects plus transactional metadata publication; account
  for object/DB partial failure, lease expiry, stale writers and orphan cleanup.
- Keep original financial conventions, sample gates, metadata, nullable missing data,
  saved drafts, revision conflicts, retry safety and private UI cache behavior.
- Local-only cache/state becomes a baseline/test adapter. New production operation and
  disaster recovery must work without the developer's disk.

## Development lanes

Lead: FastAPI, Portfolio Service, database/Auth/RLS, contracts and integration.
Data: packages/data_engine. Quant: packages/quant_engine. Frontend: compatibility and
later apps/web. Auditor: independent math/security/integration/UI verification after
integration. The agreed exact routes remain Astra xhigh lead; Terra high data/frontend;
Astra medium quant; Sol high auditor. No new workers were launched for this update.
Maximum concurrency remains lead plus three; owners cannot spawn downstream agents.

## Migration and acceptance risks

Map old Google-subject hashes to verified Supabase user UUIDs explicitly; quarantine
unmatched records. Do not upload local portfolio data as part of a GitHub sync. Export,
backup, dry-run, row counts/checksums, ownership verification and a write-fenced cutover
precede changing canonical storage. Rollback must reconcile writes made after cutover,
not silently switch to a stale SQLite snapshot. Preserve the old workspace intact.

Existing browser accessibility findings and the final integrated audit remain open.
Prior backend/quant/LPPLS results are historical evidence only and do not validate
Supabase. Core completion requires remote-persistence, RLS and Auth integration tests;
full dashboard delivery additionally requires all UI acceptance checks.

## Inputs needed at implementation time

Select the intended Supabase development project (or authorize creation), region,
Google OAuth callback/domain configuration, admission administrators, and environment
secret delivery. Project tools were not exposed here; no project connection or policy
success is claimed. These inputs do not block this architecture report.

## Review package

- [Architecture](architecture.md), [data model](data-model.md), [security](security.md)
- [Roadmap](roadmap.md), [migration](migration.md), [progress](progress.yaml)
- [Canonical requirements](../requirement.txt), [future AI scope](future-agent-runtime.md)

The existing five-hour schedule reads the latest plan and resumes authorized core work
when usage is available. GitHub remains X8xpandax8X/Quant_dashboard;
current folder is /Users/pandamac/Desktop/Quant_stock, with Documents migration pending.
