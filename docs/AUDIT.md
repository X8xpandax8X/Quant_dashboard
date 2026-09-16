# Investment Dashboard V1 independent audit

## Scope and verdict

Initial independent audit of the integrated backend, data engine, quantitative engine, authentication, persistence, and deployment assets. Frontend integration is intentionally excluded from this pass because that lane was still active.

**Verdict: fix first for the integrated V1.** The backend, data, quant, persistence, and gateway logic are ready for integration after the two confirmed implementation defects were repaired and covered by regression tests. The final verdict remains gated on the pending integrated UI/browser audit.

## Resolved findings

### 1. Resolved: the interaction contract incorrectly required 100% before Save

- **Evidence:** The API contract and approved plan require exactly 10,000 basis points for simulation, while saved records intentionally support incomplete drafts. Server behavior correctly accepts a 9,999-basis-point saved record and rejects it for `/portfolio-analytics`.
- **Resolution:** `UX-CONTRACT.md` now states that Save permits incomplete totals and zero-weight inactive rows, while simulation alone requires exactly 10,000 basis points. No backend change was needed.

### 2. Resolved: portfolio analytics labeled an incomplete result `fresh`

- **Impact:** When prices are fresh but FRED is unavailable, the portfolio response has `sharpe: null` while `meta.status` remains `fresh`. Consumers therefore receive a false data-quality signal for a result missing a required model input.
- **Location:** `app/api.py:181-196`. Status aggregation considers holding history and inherits benchmark status, but never incorporates `rf.meta.status`.
- **Reproduction:** Use deterministic fresh price fixtures and return `{"rate":null,"date":null,"meta":{"status":"unavailable"}}` from `risk_free_rate()`. A valid `POST /api/v1/portfolio-analytics` returns HTTP 200, `metrics.sharpe = null`, and `meta.status = "fresh"`.
- **Resolution:** `app/api.py` now aggregates holding, benchmark, and risk-free statuses. Required unavailable price inputs produce `unavailable`; stale/partial prices or a degraded risk-free input produce `partial`. A production-mode deterministic API regression confirms unavailable FRED returns `sharpe: null` with `meta.status: "partial"`.

### 3. Resolved: corrupt scalar cache data caused a request failure

- **Impact:** A malformed cached fundamentals or FRED JSON value raises during cache read, so the service cannot attempt a provider refresh or return an honest `unavailable` response. This breaks the required provider/cache failure behavior and can keep affected research routes failing until the SQLite cache is manually repaired.
- **Location:** `data_engine/cache.py:107-112`. `get_value()` calls `json.loads()` and `datetime.fromisoformat()` without handling corrupt rows.
- **Reproduction:** Insert `('{broken')` as `value_json` for `fred:DGS10` in `value_cache`, then call `CacheStore.get_value('fred:DGS10')`. Observed exception: `json.decoder.JSONDecodeError`.
- **Resolution:** `CacheStore.get_value()` now treats invalid JSON, timestamps, timezone-naive timestamps, and non-object payloads as cache misses. Deterministic regressions cover malformed JSON and invalid timestamp/value-shape entries, allowing the service to replace them through its normal provider or unavailable-result path.

## Verified evidence

- `.venv/bin/python -m pytest -q`: **59 passed, 1 skipped** after the audit repairs. The skip is the real Caddy gateway test when `CADDY_BIN` is not supplied in this shell.
- Quantitative review confirmed unfilled adjacent returns, 252-trading-day arithmetic annualization, sample standard deviation/covariance, 60-observation risk gates, daily conversion of the annual risk-free rate for Sharpe, CAPM scenario-price semantics, 50-bin volume profiles, and contiguous at-least-70% value areas.
- Authentication review confirmed server-derived identities behind a shared proxy secret, explicit email allowlisting, Origin plus user-bound CSRF checks on mutations, production demo-login rejection, owner predicates on all portfolio operations, and 404 behavior for other owners.
- Persistence review confirmed atomic revision predicates for update/delete, owner-scoped idempotency uniqueness, restart persistence, SQLite online backup, integrity/schema checks on restore, and a non-overwriting restore gate.
- Deployment review confirmed inbound identity/secret header stripping and gateway injection in `deploy/Caddyfile`, private Compose networking for app/OAuth services, disabled request/auth logs, and the explicit data-rights startup gate. The lead separately ran `tests/test_gateway.py` successfully against the checksum-verified local Caddy 2.11.4 binary and mock OAuth/upstream services. `docker compose config --quiet` was not run because Docker is not installed in this audit runtime.

## Remaining external verification

Real Google OAuth credentials, an excluded Google account, the full Docker Compose deployment, TLS/domain routing, and production volume recovery have not been exercised. No public deployment was performed. A later integrated UI/browser pass is still required after the frontend lane finishes.

## Supabase core checkpoint — 2026-09-17

Scope: opt-in backend Auth, private target-portfolio repository/RPC, migration RLS,
constituent eligibility, market publication leases and remote cache; typed pure quant
contracts. This does not close the broader dashboard or production acceptance gates.

Independent reviewer: observed `gpt-5.6-sol`, High, workspace-write,
`/root/core_audit`. Verdict: **ship the private checkpoint** after repairs. Lead
inspected the changes and fixed the remaining sector-normalization note. No blocking
finding remains within this reviewed path. Actual Supabase end-to-end verification
remains an explicit open acceptance condition.

Repairs: use current secret keys as API keys (not bearer JWTs); keep admission outside
market `service_role`; reject direct portfolio/registry writes; enforce active S&P
eligibility in the RPC; reject extra payload keys and nullable metadata fields; verify
Auth-admin cascading deletion; publish registry and metadata atomically under a fence.

Evidence this session:

- Python suite: 95 passed / 2 skipped before the final sector regression; final data
  suite including that regression: 15 passed. Skips are optional gateway and live
  Supabase; gateway separately passed with local listener permission.
- Embedded PostgreSQL: 38 migration/ownership/revision/idempotency/universe/fencing
  checks passed. Minimal Auth/Storage test schemas; not a real Supabase deployment.
- Frontend: typecheck, 9 unit tests, build; 4 portfolio browser flows passed against
  isolated local demo. API OpenAPI contract unchanged; 12 design tokens and fonts match.
- Independent LPPLS suite: 34 passed, no LPPLS files changed.
- Real Supabase start failed: Docker Desktop engine unable to start. No hosted project
  reference is available. Direct Data API/Auth/Storage verification remains unrun.

Astral evidence: lead Astra High; Data Terra High and Quant Astra Medium started on
verified routes, then hit usage limits. Lead completed and tested their partial edits.
Auditor Sol High route verified. No model substitution or downstream agents.

Outstanding: see SUPABASE-DEVELOPMENT.md for browser authentication, broader owned
records, retention/backoff, backups/cutover, framework migration and full UI acceptance.

### Published-version recovery addition — 2026-09-17

CLI 2.117.0 generated `20260916195011_market_version_recovery.sql`. Publication
now records immutable versions in the same transaction as the current pointer;
direct pointer/version writes are guarded. A reader checks the current artifact,
then at most three older candidates, verifying checksums and decoding metadata.
Recovery preserves original timestamps and returns stale/unavailable status.

The same independent Sol High reviewer accepted this bounded addition after repairs
for malformed value metadata and Parquet decoding failures. Evidence: **45 embedded
PostgreSQL checks** including a populated upgrade/backfill, duplicate-version rollback
and privilege checks; **10 remote adapter tests** including missing/corrupt current
objects, malformed older objects and timestamp preservation. No blocking finding
remains within this bounded review. Orphan deletion is intentionally not implemented;
real Supabase integration and the broader requirements above remain open.

Final integrated Python rerun after recovery repairs: **99 passed, 2 skipped**.
The optional gateway skip is covered by its separate passing run; live Supabase
remains unrun. No new frontend or LPPLS changes were introduced by recovery.
