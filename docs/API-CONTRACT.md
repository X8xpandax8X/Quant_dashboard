# V1 integration contract

> Baseline implementation reference. The proposed Supabase migration is documented in
> [architecture](architecture.md) and [security](security.md); it is not implemented.
> Existing API/calculation conventions remain unless explicitly superseded in root
> `requirement.txt`. Local SQLite/proxy setup here describes the current baseline only.

All routes use `/api/v1`. Frontend requests use same-origin cookies. Protected responses are `Cache-Control: no-store`. Returns/rates use fractions (0.1 = 10%); chart/UI formatting converts them to percent.

## Metadata

`meta`: `{source, as_of, retrieved_at, status, requested_window, actual_start, actual_end, currency, interval, sample_count, notes: string[]}`. Status is `fresh | stale | partial | unavailable | demo`. Price/retrieval timestamps are ISO 8601 UTC; statement observation periods may be quarter labels such as `2026Q2`, and yields use observation dates. Exchange timezone is an additional instrument property. Missing scalar fields are null, never zero-filled. Indices use `currency: "points"`; BTC and US equities use `USD`.

## Auth

- `GET /auth/me` → `{user: {id, email, name}, csrf_token, mode: demo|research|production}`; 401 when signed out.
- `POST /auth/demo` → same payload, sets HttpOnly session cookie, only allowed in demo mode.
- `POST /auth/logout` → 204, requires `X-CSRF-Token` and same Origin. Production then navigates through `/oauth2/sign_out`.
- In production Google sign-in entry is `/oauth2/start` and all normal traffic is protected by the deployment gateway.

## Instruments and research

- `GET /universe?q=&limit=50` → `{items: [{symbol,name,sector,currency,exchange,timezone}], source, as_of}`.
- `GET /markets?timeframe=1D` → `{items: [{instrument, bars, last_price, change, meta}], timeframe}`. Bars contain `{time,open,high,low,close,volume}`. Volume may be null.
- `GET /stocks/{symbol}/prices?timeframe=1Y` → `{instrument,bars,last_price,change,meta}`.
- `GET /stocks/{symbol}/analytics?peers=MSFT,NVDA&timeframe=1Y` → `{symbol, distribution, volume_profile, comparison, capm, meta}`. `timeframe` affects volume profile only; other analysis remains trailing one year.
- `GET /stocks/{symbol}/fundamentals` → `{symbol,metrics,quarters,estimate,statements,consensus,income_flow,meta}`.
- `POST /portfolio-analytics` request `{positions:[{symbol,weight_bps}]}` → `{metrics,performance,sectors,meta}`. Authentication + CSRF required. Exactly 10000 basis points, unique S&P 500 symbols, long-only, maximum 30 positions.

## Calculation output shapes

- distribution: `{daily_mean,daily_volatility,annual_return,annual_volatility,win_rate,sample_count,returns:[{time,value}],histogram:[{low,high,count}],notes:[]}`.
- volume_profile: `{poc,vah,val,coverage,total_volume,bins:[{low,high,volume}],notes:[]}`. null metrics when missing volume; estimated bar-based profile.
- comparison: `{symbols,series:[{symbol,points:[{time,value}]}],correlations:[{x,y,value,sample_count}],notes:[]}`. Fractional cumulative returns.
- capm: `{beta,risk_free_rate,market_return,actual_return,expected_return,alpha,current_price,scenario_price,sample_count,notes:[]}`.
- portfolio metrics: `{expected_return,volatility,sharpe,beta,sample_count,notes:[]}`; performance `[{time,portfolio,benchmark}]`; sectors `[{sector,weight_bps,holdings:[{symbol,weight_bps}]}]`.
- fundamental metrics: `{price,market_cap,pe,pb,eps,beta,sharpe_6m,capm_target}` all nullable numbers.
- quarters: `[{period,revenue,eps,gross_profit,operating_income,net_income,cogs,opex,taxes,gross_margin,operating_margin,net_margin,revenue_qoq,revenue_yoy,eps_qoq,eps_yoy}]`.
- estimate: `{period,revenue,eps}` or null.
- statements: `{valuation:[{label,value,unit}],income:[{label,value,unit}],balance_cashflow:[{label,value,unit}]}`; unit `currency | number | ratio | percent`.
- consensus: `{buy,hold,sell,target_low,target_mean,target_high,analyst_count}` nullable numbers; recommendation counts, not percentages.
- income_flow: `{kind:sankey|waterfall|unavailable,nodes:string[],links:[{source,target,value}],steps:[{label,value}],notes:[]}`.

## Portfolios

- `GET /portfolios` → `{items:[{id,name,positions,revision,created_at,updated_at}]}`.
- `POST /portfolios` body `{name,positions}` → saved record, 201.
- `GET /portfolios/{id}` → saved record.
- `PATCH /portfolios/{id}` body `{name,positions,revision}` → record with incremented revision.
- `DELETE /portfolios/{id}?revision=N` → 204.
- All mutations require `X-CSRF-Token`; create additionally accepts `Idempotency-Key` for duplicate-submit recovery.
- Missing/not-owned IDs return 404. Stale revision returns 409 with `{detail:{code:'revision_conflict',message}}`; frontend preserves draft, offers reload or save-as-copy.
- General errors use `{detail: string | {code,message}}`; validation errors use standard FastAPI 422.

## Python ownership boundaries

Data worker implements `data_engine.service.DataService(cache_dir: Path, mode: str)`:
- `search_universe(query='', limit=50) -> list[dict]`, `universe_symbols() -> set[str]`, `instrument(symbol)->dict`.
- `get_history(symbol, timeframe='1Y') -> HistoryResult` where dataclass has `frame: pd.DataFrame`, `meta: dict`; frame DatetimeIndex UTC and lower-case open/high/low/close/volume columns.
- `get_fundamentals(symbol)->dict` matching route output; quant-derived metric fields may initially be null.
- `risk_free_rate()->dict` `{rate: float|None, date: str|None, meta: dict}`.
- `MARKETS` exported from `data_engine.instruments`: seven instrument dictionaries, including corrected Nikkei and SET Index.

Quant worker implements `quant_engine.analytics`:
- `distribution(frame)->dict`;
- `volume_profile(frame,bins=50)->dict`;
- `comparison(frames:dict[str,pd.DataFrame])->dict`;
- `capm(frame,benchmark,risk_free:float|None)->dict`;
- `sharpe_ratio(frame,risk_free:float|None,window=126)->float|None`;
- `portfolio_analysis(frames,weights_bps:dict[str,int],benchmark,risk_free)->dict` returns `{metrics,performance}`.

Tests must use deterministic fixtures. No engine depends on app or frontend imports. Backend assembles metadata and sector exposure, validates current membership, and owns auth/persistence.

## Opt-in Supabase transport (core checkpoint)

With `QS_BACKEND=supabase`, protected endpoints require `Authorization: Bearer <user
access token>`. FastAPI validates that token through the configured Supabase Auth
server and checks Google admission, the email allowlist and current active membership.
Legacy proxy identity headers do not authenticate this backend. Response JSON schemas
and `/api/v1` routes remain unchanged.

Writes additionally require the CSRF token from `/api/v1/auth/me` and exact configured
Origin. User tokens are request-scoped; they are forwarded with a publishable API key
to the invoker portfolio RPC. Neither API payloads nor callers assign an owner. The
market-ingestion credential is isolated from portfolio requests and cannot change
membership. The browser's Supabase login/session integration is still pending.

Recovered historical market artifacts retain their observation/retrieval metadata
and report `stale`; recovery never upgrades a previously unavailable value to fresh.
