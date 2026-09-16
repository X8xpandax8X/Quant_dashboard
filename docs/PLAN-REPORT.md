# Revised implementation plan — review checkpoint

Date: 2026-09-16. Status: **awaiting review before framework implementation**.

## Decision summary

Adopt Next.js/React + FastAPI in a monorepo, preserving the existing components,
quantitative engine, providers, authentication and portfolio logic. The current
application uses React/Vite; it has not been migrated. Production remains deterministic.
Start with zero LLM endpoints; a single optional explanation endpoint can be evaluated
later. Development agents help build the product but are not deployed services.

The user selected **X8xpandax8X/Quant_dashboard** (private). GitHub connector access,
push permission and an empty remote were verified. Uploading the existing application
and revised requirements is authorized; migration and new application work remain
paused. CLI authentication and the Documents checkout are not yet established.

## Requirements reconciliation

| Source difference | Consolidated decision |
|---|---|
| Update names repository Quant_stock | Latest user selection wins: Quant_dashboard; local folder can remain Quant_stock |
| Update proposes docs/requirements.txt | Live user asks for one requirement.txt: keep it at root; no competing copy |
| Original offers multiple UI stacks | Proposed target Next.js/React + FastAPI; preserve viable React/Vite work during migration |
| Multi-agent terminology | Development roles only; production has no mandatory agent runtime |
| Original ticker, sector names, missing-volume wording | Preserve original Sections 2–4 verbatim and apply previously approved corrections in normative Section 5 |
| Uploaded checklist directs migration and implementation | Treat it as future requirements; live request requires this report first |

Original Sections 2–4 and those in the update are identical. The merged specification
retains them verbatim. The original is archived for provenance, not parallel maintenance.
No dashboard or financial calculation has been removed.

## Execution sequence after review

1. **Establish canonical checkout.** Authenticate Git transport using the approved
   GitHub account; inspect Documents parent/destination; clone the selected remote
   to `/Users/pandamac/Documents/GitHub/Quant_stock`. Verify root, origin, default and
   working branch, and select the saved project directly. Keep the Desktop source intact.
2. **Move modules with parity checks.** Move existing API/data/quant into the target
   structure, preserve public contracts and import/package boundaries, and introduce
   explicit database lifecycle ownership. Keep mechanical moves separate from fixes.
3. **Migrate frontend to Next.js.** Reuse tokens, React components, Plotly adapter,
   generated API types and query behavior. Replace Vite entry/routing/build integration;
   keep browser-only charts in client components and preserve URLs, private caching,
   CSRF, gateway authentication and API origin behavior. No UI redesign is assumed.
4. **Restore and complete verification.** Repair known contrast and small touch-target
   findings; verify portfolio failure/revision/expiry flows. Complete type/build/tests,
   contract checks, token and Premium audits, responsive browser flows and LPPLS checks.
5. **Add CI and deployment parity.** Add bounded, minimally privileged deterministic
   checks on pull requests/default-branch pushes. Update runnable web/API Compose,
   health checks and backup/restore instructions; CI does not deploy.
6. **Independent audit and handoff.** Audit mathematical, privacy, security and UI
   behavior; fix blockers, report exact commit/test/CI evidence and remaining external
   prerequisites. Deployment requires a separate authorized action and data-use rights.
7. **Measure before adding AI.** Establish request/cache/error/latency baselines. Only
   then evaluate an optional explanation endpoint. Specialist agents/frameworks require
   an accepted evidence-based architecture decision; they are outside this migration.

## Planned development team

| Lane | Exact selected route | Bounded ownership |
|---|---|---|
| Lead | GPT-6 Astra, xhigh | Architecture, auth, persistence, integration, docs |
| Data | GPT-5.6 Terra, high | Provider normalization/cache in packages/data |
| Quant | GPT-6 Astra, medium | Pure math in packages/quant |
| Frontend | GPT-5.6 Terra, high | apps/web, responsive behavior and charts |
| Auditor | GPT-5.6 Sol, high | Independent integrated review after owners finish |

Selections above are planned routes, not new observed launches. Native routing with
exact model/effort and omission of unsupported agent_type was explicitly approved.
Maximum concurrency is the lead plus three workers. Each worker gets acceptance
criteria, dependencies and sole file ownership; no downstream spawning. Astral guides
development coordination, Build Web Data Visualization guides financial evidence and
chart semantics, and Frontend Design Premium guides shared UX/accessibility. Revisit
existing approved concepts only when migration changes user-visible behavior.

## Evidence and unfinished work

The prior audit records 59 backend tests passed with one gateway skip; the lead
separately passed the real Caddy gateway check. LPPLS had 34 passing tests. Frontend
unit tests (9), typecheck and build passed during prior work. Four research browser
flows passed, including refresh/zoom and portrait/landscape checks. These are historical
observations, not a fresh verification of the uploaded checkpoint.

The accessibility run reported correlation-cell contrast and a small clear-button
hit area; calendar target sizing also needs review. Portfolio browser repairs lack a
final confirmed passing run. Final Premium/token checks and the integrated independent
UI audit remain open. Docker/real Google OAuth and production recovery were not tested.
The prior browser retry was rejected by automatic approval review because usage was
exhausted; no rejected command edits were applied. No CI or deployment success is claimed.

## Review requested

Approve the proposed Next.js migration, target structure, and phased execution above
before application work resumes. The five-hour continuation automation remains paused
so it cannot cross this review gate. GitHub upload is a reviewable checkpoint, not
approval of the migration and not a completed-release claim.
