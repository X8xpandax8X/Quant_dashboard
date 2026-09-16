# Resume investment dashboard — continuation schedule

Updated 2026-09-16. This documents the existing Codex task heartbeat; it does not
install a GitHub Actions schedule or a second scheduler.

## Configuration

- Name: **Resume investment dashboard**. Existing automation ID: `daily-brief`.
- Status: **active**, every **five hours**, attached to the current dashboard task.
- Repository: [X8xpandax8X/Quant_dashboard](https://github.com/X8xpandax8X/Quant_dashboard), private.
- Current local folder: `/Users/pandamac/Desktop/Quant_stock`.
- Future checkout: `/Users/pandamac/Documents/GitHub/Quant_stock`, only after the
  approved migration is completed and the Git root and origin are verified.
- Implementation gate: **awaiting plan approval**. Until then, check status only.
- PR #1 is merged; inspect current branches and history before selecting new work.

## Each scheduled check

1. Read the latest user instructions, `requirement.txt`, `AGENTS.md`, the plan report,
   `docs/progress.yaml`, migration notes, docs/security.md, docs/data-model.md and this document. Check current Codex limits.
2. If the plan still awaits approval, do not implement, migrate, add CI, merge or
   deploy. A quota reset or elapsed time does not constitute approval.
3. Once approval is recorded and usage is available, immediately resume authorized
   unfinished work without waiting for another prompt. If limits are exhausted,
   leave work intact for a subsequent check; never purchase or redeem credits.
4. Refresh GitHub/PR state, preserve local changes, and use a fresh bounded review
   branch. Do not reuse a merged branch blindly, force-push or merge automatically.
   Synchronize reviewed source/docs and record actual commit/test evidence. Exclude
   credentials, private holdings, caches, installed dependencies and generated output.
5. Preserve LPPLS, agreed file ownership and exact native model/effort selections.
   Continue approved integration, browser checks and independent audit until done.
6. After the approved migration, update this schedule and the docs to the verified
   Documents checkout and stop editing the Desktop reference. Do not create two
   competing authoritative copies or treat a connector upload as a local clone.
7. Pause the heartbeat when all approved work and required verification are complete.

Report meaningful progress, completion, failures or required user action; avoid
repeated unchanged status reports. Public deployment is a separate authorized action.

## Verification

The existing automation was updated through Codex's automation tool. GitHub connector
access works; local Git transport/checkout migration remains pending. This change
updates scheduling and project guidance only; no application behavior or CI was changed.

## Current architecture priority

The Supabase architecture revision supersedes the SQLite/proxy-only target. After
approval prioritize phases A–F (data, deterministic quant, owner-private Portfolio
Service, Supabase Postgres/Storage/Auth/RLS, API and tests). Defer the Next.js migration
until core parity and keep phase G as future AI documentation only. Do not interpret
this plan update or pasted implementation checklist as permission to provision cloud
resources, apply migrations, access secrets, or launch production agents.
