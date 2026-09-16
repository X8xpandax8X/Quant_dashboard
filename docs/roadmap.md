# Roadmap — Supabase core first

Architecture revision 3.0. All original dashboard requirements remain in scope.
Implementation approved 2026-09-16. Core foundation is in progress; see SUPABASE-DEVELOPMENT.md for evidence and incomplete scope.

| Phase | Scope | Acceptance |
|---|---|---|
| A | Audit existing code, contracts and canonical checkout | Reviewed module/identity/data migration mapping |
| B | Supabase Auth, admission, Postgres schemas/grants/RLS, private Storage | Reproducible migrations and actual ownership isolation |
| C | Data Engine remote repositories and freshness lifecycle | Provider/failure/concurrency/object publication fixtures |
| D | Pure typed Quant Engine | All financial fixtures and no persistence/network coupling |
| E | Portfolio Service, targets/holdings/transactions, concurrency | Atomic CRUD, direct Data API RLS, parent-owner and revision tests |
| F | FastAPI integration and minimal auth UI, deterministic CI | /api/v1 contract and dashboard compatibility checks |
| G | Future AI documentation only | No agent runtime or LLM dependency |
| Later UI | Next.js migration, remaining accessibility and responsive work | All four dashboards and independent integrated audit |
| Evidence | Telemetry, optional single AI Analyst evaluation | Representative baseline, objective quality/cost/latency budgets |
| Conditional | News/Risk/Fundamental agents, supervisor/framework | Accepted ADR with measured benefit, maintenance and rollback |

Dependencies: B precedes remote data and portfolio adapters; C and D may run in parallel
once input contracts are fixed; E uses B and preserved V1 schemas; F integrates C/D/E.
G is documentation, not an implementation gate for useful core application behavior.

## Required feature coverage

- **Markets:** all seven benchmarks, candles/change/session availability, 1D/5D/1M/1Y,
  dedicated labeled VIX gauge, timestamps and lower-resolution fallback labels.
- **Stock:** S&P 500 search, price and cumulative return, histogram mean/sample
  volatility/win rate, 50-bin OHLCV volume profile with POC/VAH/VAL, return calendar,
  normalized peers, correlation/sample counts, beta/alpha, CAPM SML/scenario zones.
- **Fundamentals:** required ratio/risk header, six-month Sharpe, historical quarterly
  revenue/EPS and growth, next-quarter estimates, margin trends, reconciled income
  Sankey or signed fallback, financial tables, analyst consensus and target range.
- **Portfolio:** constituent picker, basis-point weight editor, all eleven GICS sectors
  with persistent holdings breakdown, one-year return/covariance volatility/Sharpe/beta,
  benchmark performance and private saved CRUD/drafts/revision/expiry recovery.
- **Shared:** dark design, responsive sidebar/tabs, loading/error/empty/partial/stale/
  offline states, keyboard/touch access, table alternatives/exports, private auth,
  Yahoo/FRED ingestion and Supabase persistence, truthful missing data and method labels.
- **Extensions:** LPPLS, sector networks and three-year history interfaces, preserving
  the independent LPPLS source. Future hooks are not claims of active features.

## Validation gates

Deterministic math/provider/cache/API tests; private ownership, CSRF, auth spoofing,
revision and session tests; web lint/types/unit/build; generated-contract consistency;
responsive browser scenarios; accessibility, Premium strict audit, design token
validation; unchanged LPPLS regression. Network calls, real identities and paid model
calls are not ordinary CI dependencies. Supabase Auth/RLS/Storage and Google/TLS/recovery checks are separately
reported when their environment is available. Never turn a skipped check into a pass.
