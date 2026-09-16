# Project collaboration contract

## Current authorization and canonical path

The user requested documentation and plan review before framework implementation.
The subsequent request authorizes uploading the existing project and revised docs
to the verified private repository `X8xpandax8X/Quant_dashboard`. It does not approve
Next.js migration, new application features, CI setup, or deployment. Keep the
five-hour implementation automation paused until that plan is approved.

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
Data: `packages/data/`. Quant: `packages/quant/`. Frontend: `apps/web/`.
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
