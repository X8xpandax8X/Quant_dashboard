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
