# Data and calculation methods

## Sources and observation windows

Demo mode is deterministic synthetic data with a fixed September 14, 2026 observation date. It never calls a provider. Its intraday sessions are illustrative and do not reproduce every global exchange calendar.

Research/production use Yahoo through yfinance for prices, statements and analyst consensus, and FRED DGS10 for the annual risk-free proxy. Data is best effort: timestamps, requested/actual windows, interval, sample count and quality state accompany responses. Missing values remain null. The app does not substitute synthetic prices when live requests fail. See [yfinance's usage guidance](https://ranaroussi.github.io/yfinance/) and [FRED DGS10](https://fred.stlouisfed.org/series/DGS10).

| Selection | Requested bars | Fallback |
|---|---|---|
| 1D | Five minute | Daily, explicitly marked partial |
| 5D | Thirty minute | Daily, explicitly marked partial |
| 1M | Daily | Last valid cache or unavailable |
| 1Y | Daily | Last valid cache or unavailable |

The one-year engine fetch includes an earlier close for the first return. Analysis windows remain one year even when the price chart shows a shorter selection. Six-month Sharpe uses the latest 126 observed daily returns, subject to the minimum sample rule. The selected price window controls the approximate volume profile.

The initial constituent snapshot contains 503 share-class entries, dated September 15, 2026. The live service attempts a daily refresh and preserves a validated last-good snapshot on failure. Symbols normalize provider punctuation, such as `BRK.B` to `BRK-B`; sector aliases map to canonical GICS names. Provenance: [S&P 500 constituent table](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies), [GICS classification](https://www.msci.com/indexes/index-resources/gics).

Benchmarks are `^GSPC`, `^NDX`, `^VIX`, `^N225`, `^KS200`, `^SET.BK` and `BTC-USD`. SET Index is used directly; missing coverage does not trigger an undisclosed index substitution. Index quotes are in points; US equities and Bitcoin quotes are in USD.

## Price basis and statistics

Daily close uses Yahoo's split-adjusted price series with dividend adjustment disabled. Returns exclude dividends. Each adjacent return is `close[t] / close[t-1] - 1`. Invalid or missing prices remain gaps. Alignment happens before return calculation; missing prices are never forward-filled.

- Mean: arithmetic daily mean. Annual expected return: daily mean × 252.
- Volatility: sample standard deviation (`ddof=1`) × √252 for annual values.
- Win rate: proportion of observed returns strictly greater than zero.
- Correlation: pairwise Pearson correlation on overlapping returns; each cell reports its own count.
- Beta, CAPM, correlation and portfolio risk require at least 60 aligned returns. Zero variance yields unavailable ratios rather than division errors.
- Comparison curves share their first common observed price baseline. Shorter coverage and gaps remain visible.

## CAPM research scenario

Beta is `cov(asset, market) / var(market)` using the S&P 500 price index. Market expected return is the aligned historical daily mean × 252. The latest available DGS10 observation is divided by 100 and held constant as the annual risk-free proxy.

`CAPM return = risk-free rate + beta × (market return − risk-free rate)`.

The scenario price is `latest daily close × (1 + CAPM return)`. Historical alpha is the realized annual arithmetic return minus CAPM return. The requested “Underpriced / Alpha > 0” and “Overpriced / Alpha < 0” zones are explicitly labeled model heuristics. They do not establish fair value or predict a future price. A nonpositive or nonfinite scenario is unavailable.

## Portfolio assumptions

Positions are long-only current S&P 500 entries, with unique symbols and integer basis points. Exactly 10,000 basis points are required for simulation; saved drafts may have incomplete totals. The portfolio supports at most 30 positions.

The simulation resets to target weights daily, excluding dividends, transaction costs and taxes. All holdings and the benchmark use the same complete daily observations. Missing periods are omitted from the simulation, not modeled as flat sessions; performance compounds only the displayed common observations.

Expected return is the weighted annual arithmetic mean. Volatility is `sqrt(weightsᵀ × daily covariance × weights × 252)`. Portfolio beta is the weighted sum of aligned constituent betas. Sharpe uses daily excess returns with `daily risk-free = (1 + annual rate)^(1/252) − 1`, scaled by √252. The current risk-free observation is held constant over history.

## Volume profile and fundamentals

The volume profile is an OHLCV approximation, not transaction-level volume-at-price. Each bar's volume is assigned to `(high + low + close) / 3`. Fifty equal-width buckets are used except when every traded typical price is identical. The point of control is the highest-volume bucket. Value area expands contiguously toward the larger adjacent bucket until covering at least 70%; ties select the lower-price bucket. Invalid or missing volume is excluded, never fabricated.

Fundamentals request up to eight historical quarters plus the provider's next-quarter consensus (`+1q`). Actual coverage is reported; the live smoke check returned five MSFT quarters, marked partial. Estimates remain distinct from reported results, and missing estimates are not zero. Revenue and EPS have separate units. Margin trends divide the relevant profit by positive revenue.

A Sankey is used only when nonnegative flows reconcile at every internal node. Losses, missing components and unreconciled statements use a signed table/waterfall alternative. Provider statement labels and fiscal calendar coverage can vary by issuer; actual periods remain visible.

## Cache and extension boundaries

SQLite holds cache metadata and non-price payloads. Parquet history files use immutable version names; a transaction advances the index only after a complete file exists. A short SQLite lock coordinates readers and version retirement across processes. Request refresh locks deduplicate same-key provider fetches within the single V1 application process. Failed history requests have a five-minute retry cooldown.

The separate portfolio database is never a disposable cache. Use the documented backup/restore commands before migrations. No private holdings appear in URLs or provider requests beyond the public ticker symbols needed for analysis.

`quant_engine.models.ResearchModel` and `ModelRegistry` provide opt-in research extensions without importing the existing LPPLS project. LPPLS analysis and sector-network models can register behind this boundary in later versions. History-window configuration lives in `data_engine.service.TIMEFRAMES`; a three-year extension must explicitly extend API validation, UI labels and coverage tests. V1 does not claim to provide those future models or windows.
