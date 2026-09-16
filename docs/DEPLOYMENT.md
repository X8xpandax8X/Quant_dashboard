# Private team deployment

> Baseline implementation reference. The proposed Supabase migration is documented in
> [architecture](architecture.md) and [security](security.md); it is not implemented.
> Existing API/calculation conventions remain unless explicitly superseded in root
> `requirement.txt`. Local SQLite/proxy setup here describes the current baseline only.

The repository contains deployment configuration; no account, domain, OAuth client, or public deployment was created by this implementation.

## Single-host setup

1. Use a Linux host with Docker Compose, persistent storage, and a domain pointing to it. Only ports 80/443 are published. API and OAuth services stay on the Compose network.
2. Copy `deploy/.env.example` into a private `.env` at the project root. Replace every placeholder locally. Generate independent random proxy and OAuth cookie secrets. Never paste secrets into issues or logs.
3. Create a Google OAuth web client with exact callback `https://YOUR_DOMAIN/oauth2/callback`; configure its consent screen/test users according to your Google project. Set the client ID/secret locally.
4. Copy `deploy/allowed-emails.example.txt` to `deploy/allowed-emails.txt`, remove the example, and list actual allowed Google emails. Keep `QS_ALLOWED_EMAILS` in sync: the gateway and backend each enforce allowlists.
5. Confirm that the market-data license permits this intended shared use. Only then set `QS_DATA_RIGHTS_CONFIRMED=true`; production startup rejects false.
6. Run `docker compose config --quiet`, then `docker compose up --build -d`. Caddy provisions TLS. Verify Google sign-in, an excluded account, API unauthorized access, and two-user portfolio isolation before use.

Local development uses `scripts/dev.py`, explicitly choosing a separate demo database. Production never exposes demo login.

## Auth trust boundary

Caddy strips inbound identity/secret headers before asking OAuth2 Proxy to validate its Google session. Only successful verification supplies subject/email; Caddy injects the private proxy secret on the final upstream request. FastAPI verifies that secret and its own email allowlist. Auth cookies are Secure/HttpOnly/SameSite=Lax. State-changing API operations also require an allowed Origin and a user-bound CSRF token.

Do not publish the app or OAuth container ports, bypass the gateway, use wildcard allowlists, or run production with a development login. Keep the Compose network isolated from unrelated untrusted workloads. Changing allowed users requires updating both allowlists and restarting the affected services.

## Persistence, migration and recovery

The initial schema migration runs transactionally on startup and records version 1. Newer schemas are rejected by an older app. Future releases must add explicit version steps; back up before upgrading.

Manual local commands (use container equivalents for the named production volume):

```sh
.venv/bin/python scripts/database.py backup .state/demo/portfolios.sqlite3 /PRIVATE/PATH/portfolio-backup.sqlite3
.venv/bin/python scripts/database.py migrate .state/demo/portfolios.sqlite3
# Stop the app before restoring; this overwrites the target database.
.venv/bin/python scripts/database.py restore .state/demo/portfolios.sqlite3 /PRIVATE/PATH/portfolio-backup.sqlite3 --confirm-overwrite
```

Backups contain private user identities and portfolio holdings. No external backup service or automatic retention policy is configured. Market cache is disposable and can be rebuilt independently; never delete portfolio storage to clear prices.

## Operations

`/health` is used by the internal container health check. Monitor container restart counts, readiness, disk usage and provider error/stale states. Access and OAuth request logs are disabled to avoid recording sensitive URLs. The app does not log portfolio request bodies. Provider failures retain last-valid data with status notes. Roll back the image only to a compatible database schema; restore a verified snapshot when a schema rollback is necessary.

References: [OAuth2 Proxy configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/), [Caddy forward auth](https://caddyserver.com/docs/caddyfile/directives/forward_auth), [Yahoo usage guidance](https://ranaroussi.github.io/yfinance/).
