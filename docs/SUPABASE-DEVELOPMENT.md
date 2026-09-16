# Supabase core development checkpoint

Updated 2026-09-17. Implementation is approved. This is an opt-in foundation;
production cutover is not complete and no hosted project has been changed.

## Implemented locally

- `QS_BACKEND=supabase` validates bearer tokens through the selected project's
  Auth `/user` endpoint, then checks confirmed Google identity, the configured email
  allowlist and current active database membership on each request. Proxy headers
  cannot establish identity in this mode. User-editable metadata is not trusted.
- A request-scoped Portfolio Service forwards the user's token with a publishable
  key. It cannot use a service-role key. The invoker RPC saves normalized target
  positions, revision changes and create-retry results in one database transaction.
- The CLI-generated migration creates owner RLS, composite parent/owner constraints,
  direct-write guards and a dated constituent registry. Direct RPC writes also enforce
  active S&P 500 membership. Incomplete target weights remain valid drafts.
- Market metadata and private immutable Parquet/JSON objects use a separate server
  credential. Refresh leases fence expired writers; uploaded bytes are verified before
  publication. Universe publication updates the constituent registry atomically.
  Published versions are retained; missing/corrupt current artifacts fall back to a
  checksum-verified earlier version with stale status and original observation times.
- Market credentials have no portfolio or team-admission privileges. Admission is an
  operator SQL action. Separate secret-key strings alone do not isolate `service_role`.
- Quant functions retain existing outputs and now have typed result contracts and
  expanded deterministic edge coverage. The Vite UI and demo/legacy adapters remain.

## Local configuration

Install backend dependencies using the existing root README. The Supabase CLI used to
create the configuration and migration is pinned to **2.117.0**. Inspect command help
when changing CLI versions. There is one migration history under `supabase/migrations/`.

For an isolated local stack, with a working Docker engine:

```sh
npm exec --yes --package=supabase@2.117.0 -- supabase start
```

The attempt on this host failed because Docker Desktop could not start its engine.
Do not infer that the migration has been applied to Supabase from embedded tests.
Do not link or apply this history to a hosted project until its identity is verified.

The opt-in backend expects the following server settings, delivered through the
normal environment/secret mechanism. Never commit actual values:

- `QS_BACKEND=supabase`, `QS_MODE=research`
- `QS_SUPABASE_URL`: intended project's HTTPS base URL (loopback HTTP is test-only)
- `QS_SUPABASE_PUBLISHABLE_KEY`: a current `sb_publishable_` key
- `QS_SUPABASE_MARKET_KEY`: server-only market key, never a browser variable
- `QS_CSRF_SECRET`: independently generated secret, at least 32 characters
- `QS_ALLOWED_EMAILS`: explicit team allowlist
- `QS_PUBLIC_ORIGIN`: exact HTTPS application origin

`QS_MODE=production` also retains the confirmed data-use-rights gate. Setting the
backend flag does not finish browser Google login integration: the existing UI still
uses demo/proxy authentication. Supabase browser sign-in and refresh are pending.
API clients must provide the user's bearer token; writes also require the CSRF token
from `/api/v1/auth/me` and matching Origin. Logout revokes the current refresh session;
previously issued access tokens can remain valid until expiry. Membership removal
provides the database access kill switch and is checked on every user request.

After verifying a user's Supabase UUID and Google identity against the allowlist, an
operator with a separate database administration channel may insert/update
`public.app_members`. Do not grant this permission to the market-ingestion key. Do
not map legacy owner hashes to UUIDs by guessing, or upload private legacy records.

## Verification

Network-free application and embedded PostgreSQL checks:

```sh
.venv/bin/python -m pytest -q
npm ci --prefix database/tests --ignore-scripts
npm test --prefix database/tests
```

Embedded tests replay the actual migration using PostgreSQL through PGlite 0.5.8.
Their Auth and Storage schemas are a minimal test harness. They verify SQL behavior,
roles and policies but do not simulate Supabase's gateway, Auth server or Storage.

The actual direct Data API suite is `tests/test_supabase_live.py`. It is restricted to
an isolated loopback Supabase test stack and requires these environment variables:
`QS_TEST_SUPABASE_URL`, `QS_TEST_SUPABASE_KEY`, `QS_TEST_SUPABASE_ADMIN_KEY`, and
`QS_TEST_SUPABASE_DB_CONTAINER` (the selected local CLI Postgres container).
It creates synthetic users through Auth, provisions admission through local operator
SQL, tests user Data API attempts, and cleans up the synthetic Auth users. Do not use
real accounts or a hosted project for this fixture. No test keys belong in Git.

## Remaining work before core completion

- Actual Supabase migration replay, direct Data API isolation, Auth and Storage tests;
  hosted project reference and Google provider/callback configuration remain pending.
- Browser sign-in, refresh, logout/cache behavior and session-expiry integration.
- Broader relational profiles/holdings/transaction boundaries and migration/import
  tooling. Only scenario target positions are currently implemented.
- Orphan-object collection with reader-safe retention;
  failed publications deliberately leave unreferenced immutable objects for now.
- Exchange-aware freshness, cross-process negative backoff and complete provider
  throttling/concurrency scenarios. Current TTLs preserve baseline behavior.
- Remote backup/restore, verified identity mapping and a write-fenced cutover.
- Git-authenticated canonical Documents checkout, CI, later Next.js migration,
  full responsive/accessibility verification and final integrated audit.

No worker output, embedded test or private GitHub checkpoint implies these gates passed.
