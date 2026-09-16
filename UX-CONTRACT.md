# V1 shared interaction contract

Business sources: `requirement.txt`, user-approved implementation plan, `docs/API-CONTRACT.md`.

## Canonical owners

Frontend shared primitives own buttons, fields, symbol Combobox, Tabs, Select/Listbox, Dialog, Toast, chart panel and data table. Global CSS owns scrollbar appearance. React Router owns committed view state; TanStack Query owns fetched state and invalidation. Backend owns validation, identity, portfolio ownership and revisions. Table selection is not needed in V1.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Button | components/ui.tsx Button | DESIGN.md and shared CSS | Default, primary, danger, ghost | Keyboard activation, focus and browser action checks |
| Select/Listbox | SymbolSearch and Radix SelectField | components/SymbolSearch.tsx and components/ui.tsx | Searchable symbols and fixed local options | Arrow/Enter/Escape, accessible names, cancellation |
| Form | Shared field styles and PortfolioPage | Portfolio validation and API schema | Portfolio name, basis-point weight inputs | Invalid inputs, failed save and draft recovery |
| Dialog | Radix Modal and ConfirmDialog | components/ui.tsx | Navigation, unsaved changes, deletion | Focus trap, Escape, Cancel focus and restoration |
| Tabs | Radix AppTabs and TabPanel | components/ui.tsx and route query state | Research and statement tabs | Keyboard arrows, URL restoration, active content only |
| Table | Semantic tables and ChartPanel data alternative | components/Chart.tsx and statement rows | Read-only data, paginated chart observations | Correct units/values and keyboard access |
| Scrollbar | Global CSS | styles/tokens.css | Page scroll and bounded table overflow | Phone/landscape overflow and contrast checks |
| Toast | ToastProvider | components/ui.tsx | Success and recoverable-error feedback | Polite live region and persistent inline errors |
| CRUD | PortfolioPage and owner-scoped API | docs/API-CONTRACT.md | New, open, rename, save, copy, delete | Actual browser persistence/error/conflict tests plus API isolation tests |
| Chart | Shared Plotly adapter | components/Chart.tsx and CSS tokens | Candles, bars, lines, matrix, gauge, flow, donut | Resize/zoom, complete data alternatives and export provenance |

## Navigation and state

Routes `/markets`, `/stocks/:symbol`, `/fundamentals/:symbol`, `/portfolio`. Preserve symbol across stock and fundamentals screens. URL contains timeframe/tab/peer state, never holdings or weights. Default market range 1D; stock price range 1Y. Analytics retain an explicit 1Y badge. Sidebar collapse is a small local preference. Saved portfolios stay on the server; a recoverable draft may use tab-scoped session storage keyed to the authenticated owner. Never put private holdings in localStorage. Explicit logout and user changes clear private drafts and fetched data.

## Research behavior

Loading reserves final geometry with a spinner; refresh preserves data and chart zoom. Empty, unavailable, partial, stale, offline and errors are separately labeled with a recovery action where useful. Poll visible intraday views every five minutes. Do not poll hidden browser tabs. Cancel obsolete searches; debounce remote search 300ms, honor IME and immediate clear/Enter. Essential chart values work without hover. Mobile has tap/focus details and keyboard chart-table alternatives. Respect reduced motion.

## Portfolio workflow

Open a saved portfolio into a draft. Edit weights and Save at any total so incomplete allocations can remain drafts; symbols stay unique and weights remain whole basis points from 0 to 10,000. Require exactly 10,000 basis points only to run simulation explicitly, with zero-weight rows treated as inactive. Ordinary Save stays in the editor with success feedback; create selects the new saved portfolio. Cancel/reload discards drafts only after an app-owned unsaved-change confirmation. Revision conflicts keep draft and offer Reload or Save as copy. Save is idempotent and prevents duplicate submission. Delete confirms named portfolio and permanent consequence; focus Cancel initially. Records remain saved until owner deletion. Unauthenticated/expired session clears fetched private caches while retaining the owner-keyed draft for same-user reauthentication; switching users discards that draft.

## Authentication and privacy

Google email allowlist, no registration. Server-derived identities and owner filters on every read/write. CSRF on writes. Production never enables demo login. Demo is an explicit local mode with clearly illustrative data and separate data directory. Logout clears query caches and drafts. No holdings, credentials or tokens in URLs, logs, analytics or toasts.

## Accessibility and feedback

WCAG 2.2 AA. Native buttons/links/table semantics; visible focus; authored controls with expected keyboard behavior. Dialogs manage focus, Escape and restoration. Every icon action has an accessible name. Forms use noValidate with associated field errors. Shared polite live-region feedback, persistent inline errors, stable busy buttons. All data visualizations provide a caption and accessible table. No browser alert/confirm/prompt.
