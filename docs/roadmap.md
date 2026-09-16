# Roadmap and acceptance gates

Delivery sequencing retains every feature in requirement.txt Sections 2–5.

| Phase | Scope | Exit evidence |
|---|---|---|
| 0: current checkpoint | Merge requirements, update docs, upload baseline to selected private GitHub | Preserved source scope, reviewed upload inventory, verified remote commit; plan report |
| 1: foundation | Canonical checkout, package migration, Next.js shell, API/storage parity, deterministic CI | Verified root/origin; locked builds; imports/contracts/auth/math tests |
| 2: all dashboards | Markets; stock price/distribution and peers/CAPM; fundamentals; private portfolio | Full data/state/interaction flows and independent audit |
| 3: evidence | Request category, latency, failures, fallback/cache outcomes and quant validation | Representative baseline with sample coverage and budgets |
| 4: conditional specialists | Only categories with measured quality/cost/latency benefit | Accepted ADR, evaluation thresholds, rollout/rollback |
| 5: conditional framework | Only demonstrated state/recovery/branching/parallelism needs | Accepted ADR showing benefits exceed operational complexity |

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
  Yahoo/FRED cache, truthful missing data and method labels.
- **Extensions:** LPPLS, sector networks and three-year history interfaces, preserving
  the independent LPPLS source. Future hooks are not claims of active features.

## Validation gates

Deterministic math/provider/cache/API tests; private ownership, CSRF, auth spoofing,
revision and session tests; web lint/types/unit/build; generated-contract consistency;
responsive browser scenarios; accessibility, Premium strict audit, design token
validation; unchanged LPPLS regression. Network calls, real identities and paid model
calls are not ordinary CI dependencies. Google/TLS/Docker/recovery checks are separately
reported when their environment is available. Never turn a skipped check into a pass.
