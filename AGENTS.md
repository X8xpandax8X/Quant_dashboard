# Project collaboration contract

## Current authorization and canonical path

The user approved the Supabase core implementation on 2026-09-16 by explicitly
requesting “continue implementing” after the plan review. Proceed with phases A–F
and local tests; Next.js follows core parity. The existing five-hour schedule resumes
authorized work when usage is available. Hosted Supabase changes require the existing
project reference the user is providing. No public deployment or automatic PR merge.
The selected private GitHub upload remains authorized. Desktop remains the working
source until Git transport and the Documents checkout are verified.

`requirement.txt` at the repository root is the sole canonical specification;
`docs/reference/requirement.original.txt` is an immutable provenance archive.
Read `docs/PLAN-REPORT.md`, `docs/migration.md`, and `docs/progress.yaml` first.
Current source: `/Users/pandamac/Desktop/Quant_stock`.
Planned canonical checkout: `/Users/pandamac/Documents/GitHub/Quant_stock`, pending
migration and verification. After migration use that saved project directly in its
local checkout; preserve the Desktop source as a read-only reference. Never claim
it is migrated just because a remote branch exists.

Inspect root/origin/branch/status before Git changes. No force pushes, auto-stashing,
hard resets, unrelated commits or nested repositories. Upload only reviewed source,
fixtures, dependencies' manifests/locks and documentation; exclude secrets, user
state, fetched market data, caches, generated builds and installed dependencies.

## Product and boundaries

Implement `requirement.txt` and the user-approved V1 plan. React + FastAPI, private Google-allowlisted team, owner-private saved portfolios. Preserve `LPPLS/` entirely. Do not publish publicly, deploy, create external accounts, or inspect unrelated credentials. The selected private GitHub upload is authorized.

## Ownership

- Lead: `app/`, root manifests, architecture/contracts, integration, deployment, documentation and root tests.
- Data worker: `data_engine/` including its tests and constituent assets.
- Quant worker: `quant_engine/` including its tests.
- Frontend worker: `frontend/` including frontend tests. Read `DESIGN.md`, `UX-CONTRACT.md`, and `docs/API-CONTRACT.md` before edits.
- Independent auditor: inspect integrated work; narrowly repair confirmed issues and rerun affected checks.

You are not alone in the workspace. Preserve concurrent changes. Do not modify another lane's files without lead coordination. Do not spawn downstream agents. State exact model/effort/runtime evidence in handoffs; do not silently replace a requested route.

## Required checks

Use network-free deterministic tests for quantitative math, providers/cache failure, and API authorization. Cover owner isolation, CSRF, draft preservation, revision conflicts, price/return basis, missing data, and zero variance. Frontend typecheck/build and browser checks must pass. Run existing LPPLS tests without changing its files. A fresh independent review is required before completion.

## Data and security

Never fabricate live prices or missing fundamentals. Demo responses are explicitly labeled `demo`. API metadata includes source and observed/retrieved timestamps. User IDs come from verified authentication, never request JSON. Never log authentication tokens or private holdings. Shared deploy is explicitly gated on data-use rights.

## Approved-plan migration ownership (future)

Lead: `apps/api/`, `database/`, root configuration, shared integration tests and docs.
Data: `packages/data_engine/`. Quant: `packages/quant_engine/`.
Lead also owns `packages/portfolio_service/`, Supabase migrations/Auth/RLS and storage
contracts; data owns market repositories/object storage only. Frontend: `apps/web/`.
Until migration, the existing ownership paths above still apply. No downstream
agents. At most the lead plus three workers concurrently; the auditor follows
integration. Use the user-approved exact native model/effort routes: lead Astra
xhigh, data Terra high, quant Astra medium, frontend Terra high, auditor Sol high.
Recheck actual routes before launches; distinguish selections from observed runs.
Production contains deterministic services, never these development workers.

Use the actual commands in README.md for baseline checks; after migration update
commands and paths atomically. Done means all requirement features are verified or
explicitly source-unavailable, private portfolios remain isolated, required checks
pass, and an independent audit has no open blocking findings. A GitHub upload is
only a checkpoint. Future-agent placeholders do not count as implemented runtime.

## Supabase target and priority

Read docs/architecture.md, docs/data-model.md and docs/security.md. Immediate approved-
implementation priority, once review is complete: Supabase foundation, Data Engine,
pure Quant Engine, Portfolio Service and FastAPI integration/tests. Next.js follows
core parity. Preserve working modules; no production AI runtime or new UI feature work.
Supabase is canonical for production state/history; local disk is only a baseline,
demo fixture or disposable buffer. User requests must exercise database RLS using the
validated user context, never a service-role/BYPASSRLS portfolio client. Preserve the
Google team allowlist, private drafts, basis-point targets and revision/idempotency rules.
Test actual policies through direct Data API attempts, not just API WHERE predicates.
Use Supabase skill and current documentation; create migrations through the CLI's
verified commands. Keep a single migration history and never invent migration filenames.
