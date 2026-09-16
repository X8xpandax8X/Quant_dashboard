# Proposed Supabase data model

Target model. A CLI-generated foundation migration has passed embedded PostgreSQL checks; no hosted migration has been applied. Broader tables below remain planned. Use a shared database with owner
columns, never one database per user. Supabase Auth user UUIDs are canonical identities.

## Portfolio and membership tables

| Table | Principal fields and invariants | Scope |
|---|---|---|
| app_members | user_id -> auth.users, active, admitted_at; only trusted administration may change admission | Admission check, user can read only own status |
| profiles | id -> auth.users, display_name, created_at/updated_at; no editable authorization flags | Own row |
| portfolios | UUID id, owner_id -> auth.users, name, base_currency, revision >= 1, timestamps | Own rows; unique (id, owner_id) |
| portfolio_positions | portfolio_id, owner_id, symbol, target_weight_bps integer 0..10000 | Existing V1 scenario positions; unique (portfolio_id, symbol) |
| holdings | id, portfolio_id, owner_id, symbol, quantity, optional cost_basis, currency, as_of | Recorded holdings, distinct from target-weight scenarios |
| transactions | id, portfolio_id, owner_id, symbol, type, quantity, price, currency, executed_at, metadata | Owned transaction records; no trading execution |
| watchlists / watchlist_items | id or parent_id, owner_id, symbol, timestamps | Planned additional owned records after core portfolio parity |
| portfolio_settings | portfolio_id, owner_id, settings with validated keys/schema version | Per-portfolio preferences |
| portfolio_write_requests | owner_id, idempotency_key, request_digest, resulting portfolio/revision | Unique (owner_id, idempotency_key); retry-safe writes |

For every child table, composite foreign key (portfolio_id, owner_id) references
portfolios(id, owner_id), so a child cannot claim another user's parent. Owner fields
are immutable through user-facing mutations. Index owner_id, owner_id/updated_at,
child portfolio_id/owner_id, and transaction portfolio_id/executed_at as queries need.
Use timestamptz and explicit currency/unit columns. Use exact numeric types for
quantities/prices/costs; preserve null cost basis when unknown.

**Targets are not holdings.** Preserve the existing basis-point API and incomplete
saved drafts. Exactly 10,000 basis points is a simulation precondition, not a draft
save constraint. Do not infer shares, cost basis or historical trades from weights.
Holdings/transaction repository boundaries and isolation tests belong in Phase E;
automatic ledger reconciliation, realized P&L, tax-lot accounting and new dashboard
workflows require separate requirements. Declare whether holdings are manual snapshots
or ledger-derived before implementing reconciliation; never make both authoritative.

Portfolio save replaces target rows and increments the parent revision atomically.
Use a transactional SECURITY INVOKER RPC for multi-table mutations with the user's
JWT. Compare the expected revision, enforce ownership/RLS, return a typed conflict,
and commit idempotency outcome together. A denied owner sees not-found/denied without
learning another user's row. Validate row count, unique symbols, long-only values,
S&P 500 eligibility and payload limits in the service, with suitable SQL constraints
or the transactional RPC for invariants that direct Data API writes could bypass.
Grants must expose only the operations required by this contract.

## Shared market tables

| Table | Key data |
|---|---|
| instruments | Canonical symbol, provider symbol mappings, type, exchange/timezone, currency |
| constituent_snapshots / members | Dated universe with source provenance, canonical sectors and validity |
| company_metadata | Instrument, observation/retrieval dates, schema version and validated fields |
| fundamentals | Instrument, period, statement/estimate kind, units, source and nullable values |
| market_data_metadata | Dataset key, interval/window, immutable object key/version, checksum, coverage, quality and sample count |
| data_refresh_status | Dataset key, last attempt/success, next due time, errors/backoff, lease token/expiry |
| analytics_metadata | Method/version, input dataset versions, windows, quality and timing; no shared private holdings |

Market tables are shared team data, not owned by a single investor. Browser writes
are denied. Shared market reads require active admission if exposed. Provider refresh
writes use a separately scoped ingestion principal/repository. Keep refresh internals
in an unexposed schema where practical. User-specific analytics caching, if added,
requires owner_id and the same RLS boundary as portfolio state.

## Storage object design

Private bucket `market-data` with configurable prefixes equities/, indexes/,
benchmarks/ and other-timeseries/. Keys include dataset identity and immutable version;
no credentials or private portfolio payloads in filenames. Persist bucket/key/checksum,
format version and row/coverage metadata in Postgres. Do not store expiring signed URLs
as canonical references. Read via authorized server storage access; issue short-lived
links only for a separately authorized export requirement.

A source fetch produces a new object. Publish the pointer only after upload verification.
On partial failure keep the last valid reference. Garbage collection removes only
unreferenced versions older than a retention/grace threshold; backup and restore
procedures must cover both database metadata and the referenced Storage objects.
Database backup alone is not treated as proof of artifact recovery.
