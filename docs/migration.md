# Migration inventory and repository connection

Observed 2026-09-16.

## Verified state

- Source: `/Users/pandamac/Desktop/Quant_stock`; no Git root was present during inventory.
- Target remote: `https://github.com/X8xpandax8X/Quant_dashboard.git`, private;
  connector authenticated as X8xpandax8X with push/admin access.
- Initial remote inspection: empty repository, no branches; configured default `main`.
- Planned checkout: `/Users/pandamac/Documents/GitHub/Quant_stock`; absent at inventory.
  Documents and Documents/GitHub exist and were not Git roots. No collision found.
- GitHub CLI exists but is not authenticated. Connector access is a separate working
  transport. No credentials were read or copied to the project.
- The user explicitly authorized uploading this project. Establish a minimal README
  on the empty default branch, upload the reviewed baseline on a feature branch, and
  provide a draft pull request. No merge, CI setup, code migration or deployment.
- Intended upload branch: `chore/requirements-and-project-baseline`. Record actual
  remote outcome in the handoff; a planned branch name alone is not verification.

## Reviewed mapping

| Existing source | Proposed destination | Treatment |
|---|---|---|
| frontend/ | apps/web/ | Reuse components/tokens/query/tests; migrate Vite and React Router boundaries to Next.js |
| app/ | apps/api/ | Preserve API/auth/private CRUD, define package imports |
| data_engine/ | packages/data/ | Preserve providers/cache/assets and tests |
| quant_engine/ | packages/quant/ | Preserve deterministic engine/fixtures and extension registry |
| app/db.py + scripts/database.py | apps/api + database/ | Keep service interface; isolate schema/migration/lifecycle responsibilities |
| tests/, docs/, scripts/ | same logical roles | Update paths/commands only with parity checks |
| compose.yaml + Dockerfile + deploy/ | docker-compose.yml + service builds + deploy/ | Adapt to separate Next.js/web/API services after runnable builds |
| LPPLS/ | LPPLS/ | Preserve source entirely, independent tests/runtime |

Current source/manifests/locks, static constituent snapshot, tests, docs/concepts and
application font assets belong in the reviewed baseline. Exclude virtualenvs,
node_modules, caches, local database/user state, .env, allowlist contents, test traces,
build outputs and generated LPPLS dashboard output. Retain excluded files locally.
No secret, cache or user portfolio is part of the upload. This is an initial baseline,
so prior implementation history cannot be reconstructed or claimed.

## Canonical checkout is still pending

Uploading via the connector does not create or verify a local Git checkout. After
plan approval, establish Git transport, clone the selected remote, inspect fetched
refs, select the working branch, and verify root/status/origin/remote refs. Use the
saved Documents checkout directly for subsequent work. Preserve the Desktop source
as read-only after migration; do not maintain two authoritative working copies.

Do not modify an unrelated origin, auto-stash, hard-reset, force-push, copy .git
metadata or delete the old workspace. Inventory destination again before writing.
Any new remote changes must be reconciled without overwriting them.

## Verified GitHub upload checkpoint

The selected private repository now contains the current project on
`chore/requirements-and-project-baseline`. [Draft PR #1](https://github.com/X8xpandax8X/Quant_dashboard/pull/1)
targets `main` and remains unmerged. Bootstrap commit:
`bc45fae18f9d71de4434ccaa5194612e3cfe90e2`. Application/requirements baseline commit:
`99c91ba5834680909f6f02e35210d9be971634eb`.

All 111 reviewed baseline files produced local tree hash
`0b4852606dd24627460b03abe73378ff75400d59`, exactly matching the GitHub tree.
The inventory is recorded in [verification/upload-manifest.json](verification/upload-manifest.json).
Checks confirmed source Sections 2–4 were preserved, progress IDs/schema were valid,
and the secret-pattern scan found no matches. These are upload/document checks,
not a new application verification run.

The initial combined tree request exceeded automatic approval review's 200 KB limit.
Smaller reviewable tree batches succeeded; the resulting full tree was checked
against the local manifest before the branch was updated. No force update was used.
CI has no configured workflow or reported checks for this baseline. This is not a
CI pass. GitHub access/upload uses the authenticated connector; local Git transport
and migration to Documents remain pending the plan review.
