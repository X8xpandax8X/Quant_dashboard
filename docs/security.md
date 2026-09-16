# Proposed Supabase security boundary

Planning only. Validation below is required before declaring Supabase isolation complete.

## Authentication and admission

Use Google through Supabase Auth; keep the team's explicit email allowlist. A trusted
admission flow checks verified provider identity against that allowlist, then provisions
app_members by Supabase user UUID. Disable anonymous sign-in and unneeded providers.
Unlisted accounts cannot gain application access merely by obtaining a valid JWT.
User-editable profile/user_metadata is never an authorization input. Provisioning and
membership edits are administration-only; normal users cannot admit themselves.

FastAPI validates signature using an allowlisted algorithm and the configured project's
JWKS, plus issuer, audience, expiry/not-before and a valid subject. Support key rotation
and bounded key caching; reject tokens for another project. Prefer asymmetric signing;
legacy symmetric projects need an Auth-server verification path. Do not decode and trust
claims without validation. This follows [Supabase JWT guidance](https://supabase.com/docs/guides/auth/jwts).

Gateway headers cannot choose a user. Normal portfolio requests forward the validated
user's access context through an isolated/request-scoped Supabase Data API client and
publishable key. Never mutate shared global client sessions across users. Do not route
owner reads/writes through service-role keys, migration credentials, postgres or another
BYPASSRLS role. Any isolated privileged ingestion/provisioning credential is server-only,
separate from Portfolio Service and excluded from logs/frontend bundles.

## Database enforcement

Every exposed table receives deliberate grants and enabled RLS. For owned records,
SELECT/DELETE require active membership and auth.uid() = owner_id. INSERT checks the
new owner; UPDATE checks both the existing and resulting owner plus membership.
SELECT permission is also needed for updates. Apply policies to authenticated with
explicit ownership predicates; role membership alone is insufficient. Use the same
owner boundary for direct Data API requests and transactional invoker RPCs.

app_members allows users to read their own membership status only; trusted administration
owns mutations. Owned-row policies check its current active status, so removing admission
blocks new operations without waiting for old JWT claims to refresh. Composite child
foreign keys enforce parent/owner consistency. Audit profiles, target positions,
holdings, transactions, watchlists/settings and idempotency records individually.

Prefer invoker functions and invoker views or unexposed views. No SECURITY DEFINER
shortcut for permission errors. Review function execution grants, search_path, view
privileges, owner-transfer attempts and service-role bypass separately. The policy
mechanics follow [Supabase RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Storage and secrets

Keep market-data private; browsers cannot upload, overwrite or delete canonical history.
Scope the ingestion storage path explicitly and test denied alternate buckets/prefixes.
Service credentials bypass Storage policies, so using one is a privileged administrative
boundary, not evidence that RLS works. Prefer immutable uploads. If upsert is introduced,
verify all required operation permissions. See [Storage access control](https://supabase.com/docs/guides/storage/security/access-control).

Proposed public settings: project URL and publishable key. Proposed server-only settings:
JWT issuer/audience, configured storage bucket/prefixes, and separately scoped ingestion/
provisioning credentials if required. Migration database credentials are deployment-only.
Do not fill example values with real secrets or use NEXT_PUBLIC_ for privileged material.
No environment files are changed in this planning checkpoint.

## Browser/session behavior

Minimal existing-React integration signs in through Supabase and sends a bearer token
to FastAPI; preserve private cache clearing and drafts on expiry. OAuth uses approved
redirects and PKCE/state checks. For later Next.js SSR, validate identity server-side,
coordinate token refresh, and keep session/private responses out of shared caches.
A raw getSession user object is not proof of identity. See [Supabase SSR guidance](https://supabase.com/docs/guides/auth/server-side/creating-a-client).

Retain strict origin/CSRF checks wherever cookies authenticate writes, including future
server actions; bearer-only endpoints must not silently accept ambient cookies. Redact
Authorization/cookies/holdings from logs. Logout clears client session and user query
caches; do not claim issued JWTs become instantly invalid. Use membership revocation
for immediate team-access removal and test the chosen session revocation/expiry policy.

## Required security tests

- Real local Supabase/Postgres policies with users A and B, unauthenticated callers,
  and an authenticated but unadmitted user; mocks alone cannot prove RLS.
- Direct Data API SELECT/INSERT/UPDATE/DELETE attempts against every owned table,
  another owner's UUID, forged owner fields, owner transfer and cross-owner parents.
- JWT wrong project/signature/algorithm/expiry, refresh/key rotation, membership removal,
  session expiry and attempted identity-header spoofing.
- Multi-user concurrent requests cannot leak a reused client session. Normal private
  endpoints never instantiate a privileged client; exercise invoker RPCs under real RLS.
- Retry/idempotency conflicts, concurrent revision updates, rollback after child-write
  failure, draft recovery and private query cache clearing on logout/account switch.
- Storage list/read/write/overwrite/delete by allowed and denied principals; missing
  objects, orphan uploads, stale metadata, checksums and recovery from backup.
- Run Supabase security/performance advisors and examine grants/views/functions/storage;
  investigate findings before accepting the foundation.
