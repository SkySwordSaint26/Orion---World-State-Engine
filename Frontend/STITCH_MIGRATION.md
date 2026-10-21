# Stitch migration and acceptance report

Branch: `redesign/stitch-frontend`.
Rollback baseline: `codex/ledger-workflows` at `2ba5f5c`.
Implementation is published on `redesign/stitch-frontend`; no deployment or production-data changes were made.
All pre-existing untracked manuscripts, presentation files, extraction experiments, tests and the design ZIP were preserved.

## Screens and preserved workflows

| Screen | Redesign | Preserved access |
| --- | --- | --- |
| Sign-in | Shared Nocturne typography and palette | Sign-in, registration and validation; forgot-password, fingerprint and public-key placeholders unchanged |
| Worlds | Featured chronicle, archive cards, quiet navigation rail | Open/create/delete worlds and logout |
| New world | Genesis form, blank creation and import panels | Name/description defaults, manuscript/material import, file browsing and drag/drop |
| Overview | Codex portals, manuscript hearth, real world counts | Graph, ledger, manuscripts, timeline, contradictions, character dialogue, quick entity creation and session archive log |
| Manuscripts | Ingestion panel and chapter archive | Upload, expansion, word counts, chapter navigation and confirmed deletion |
| Processing | Inscription progress with actual job status/counts | Completion/error states, background navigation; backend cancellation now implemented |
| Ledger | Editorial register with category/search controls | Selection, select-all, survivor selection, merge, bulk deletion, creation, event counts and Timeline link |
| Entity inspector | Warm dossier styling | Description edit/cancel/clear, type changes, traits, aliases, facts, directed relationships and chapter appearances |
| Writing room | Chapter index, reading column, passage astrolabe, focus controls | Read/edit/save/cancel, rerun, chapter creation/deletion, history, highlighted entities, citation offsets, selection-to-entity/location/event workflows |
| Extraction review | Accessible review dialog | Explicit selection, dependency blocking, preference-based preselection, changed values defaulting to keep-old, ordered apply, discard and partial-error reporting |
| Graph | Constellation controls and responsive inspectors | Search, filters, node movement, zoom/pan/fit, directed connections, Escape cancellation, chapter snapshots, relationship CRUD and version history |
| Timeline | Chapter folios, character journeys and responsive event inspector | Chapter/participant/text filters, unassigned events, participant roles/statistics, create/edit/delete, within-chapter order and manuscript links |
| Contradictions | Restyled evidence/decision workspace | Open/resolved/rejected records; keep old/new fact or relationship, acknowledge, reject, restore and source links |
| Assistant | Nocturne dialogue workspace | World/character focus, recent history, preset prompts, citations and visible service errors |
| Profile/settings | Native modal dialogs with keyboard focus and Escape dismissal | Pen name, account counts, password, logout, world settings/deletion, chat length and review preferences |

## Requested fixes

- Traits are sent as the existing versioned `traits` attribute and read back from active fact values after reload.
- Entity updates verify that returned values match the requested changes. Failed writes retain input and show the author an error.
- Fact creation reloads the persisted entity, preserving actual fact IDs and accepted values. Failed fact additions/deletions no longer change local state as if they succeeded.
- Chapter saves confirm stored text before updating the local chapter or leaving edit mode. Editing and saving remain available while extraction runs; the editor monitors the latest requested extraction.
- Chapter History previews stored version text. Restoring creates a new version and queues the existing propose-then-review extraction workflow; older versions and accepted world facts remain intact.
- Import cancellation persists a cancelled job/run state, prevents remaining integration, stops and reaps an active extractor subprocess, and preserves completed chapters. The worker checks cancellation about once per second; an already-committing chapter finishes atomically.
- EPUB is removed from file pickers and rejected by the backend before file storage. TXT, Markdown, DOCX and PDF remain available.
- Failed contradiction decisions remain retryable. Timeline save failures are visible within the event dialog. Saved world settings immediately update the displayed world.
- The stored chat reply-length preference now reaches the chat service through the HTTP route.

## API additions

Existing clients and routes are retained. The authorized backend additions use existing string status columns and chapter-version storage; no models or migrations changed.

- `POST /api/v1/jobs/{job_id}/cancel`: owner-scoped, idempotent cancellation. Status endpoints can return `cancelled`. Completed/failed jobs retain their terminal status.
- `GET /api/v1/worlds/{world_id}/chapters/{chapter_id}/versions/{version_id}`: owner/chapter-scoped version metadata plus stored text; unavailable stored text returns a visible conflict response.
- `POST /api/v1/worlds/{world_id}/chapters/{chapter_id}/versions/{version_id}/restore`: appends a new version and returns the existing re-extraction job response.
- EPUB uploads return `415`.

Frozen routing, shared fixtures, models, Alembic migrations and `docs/api.md` were untouched. No dependencies were added or removed.

## Verification

The baseline passed 426 backend tests, the original 10 browser regressions and a production build before implementation.

Final checks passed in the working checkout, including pre-existing untracked extraction tests that were left out of these commits:

- 434 backend tests, including real registration/login, owner scoping, persisted cancellation, cancellation timing, real child-process termination, traits and immutable historical restoration.
- 30 browser tests, including the original 10 regressions, persistence/error retries, cancellation, historical restoration, review dependencies, timeline CRUD/order, authentication, settings, and saving during background extraction.
- Production frontend build.
- Frontend lint: zero errors, 21 warnings remain.
- `git diff --check`.

Visual checks capture 11 routes at 1440, 900 and 390 pixels, checking overflow and runtime errors. Screenshots are generated under `Frontend/test-results/visual-parity-*` and are intentionally ignored by Git.

The linter now targets project code rather than dependencies and invokes its Node entry point, avoiding the Windows PowerShell shim issue. Existing lint/deprecation warnings and Vite's bundle-size warning remain; they are not disabled.

## Deliberate design adaptations

The ZIP contains alternative navigation and dashboard concepts. This implementation uses one consistent navigation rail and retains every existing URL and workflow.

Calendar years, lifespans, lore-coherence/tension scores, session quotas, export, timeline forks, file watchers, Scrivener/Obsidian synchronization and automatic canon fixes are not backed by the existing application. Their sample claims/data were not copied into the product. The timeline and graph remain chapter-based; real loading, empty and error states replace prototype sample content. Decorative supplied portraits and sample lore are not assigned to user entities.

The entity inspector retains its existing overlay behavior. The full contradictions page and character assistant remain directly accessible, even though the export often presents only embedded summaries. A live GPU extraction-cancellation smoke test against an author's manuscript was not performed; cancellation is covered by isolated database tests and a real child-process termination test without models.

## Preview

From the repository root, in PowerShell:

```powershell
Set-Location Frontend
npm.cmd --script-shell=cmd.exe run dev -- --host 127.0.0.1 --port 5173
```

Development API requests use the frontend's own `/api/v1` path. Vite proxies them to `VITE_API_BASE_URL`, defaulting to `http://127.0.0.1:8000/api/v1`; this works when the frontend uses port 5174 as well as 5173. A separate API origin can still be configured for production builds. No author database was seeded or reset. Production checks use:

```powershell
npm.cmd --script-shell=cmd.exe run build
npm.cmd run lint
$env:PLAYWRIGHT_CHANNEL = 'msedge'
npm.cmd --script-shell=cmd.exe run test:e2e
```

The browser tests use isolated API fixtures, never an author's database. The backend tests also use isolated fixture storage/databases.

Authentication follow-up: requests from port 5174 previously failed the backend's CORS preflight. The development proxy now honors the configured API address without cross-origin browser calls. Login waits for `/auth/me` before authenticating; failures clear provisional tokens, retain the form and credentials, and show an error. Authentication requests have a 15-second deadline.

Live verification on port 5174 passed: registering the existing demo email displayed the correct duplicate-account explanation, then demo login and `/auth/me` both returned 200 and opened the archive. New-account registration was verified against isolated storage; existing account passwords and world data were preserved.

## Safe rollback

The redesign is isolated on `redesign/stitch-frontend`. The original branch and baseline commit are preserved. Leave unrelated local files and uncommitted work intact when switching branches.

To review the published UI in another clone:

```powershell
git fetch origin
git switch redesign/stitch-frontend
```

Use a separate baseline checkout, for example from the repository root (the target must not already exist):

```powershell
git worktree add --detach D:/Orion---World-State-Engine/tmp/stitch-baseline-checkout 2ba5f5c
```

This leaves the redesign and unrelated untracked work untouched. Published implementation commits can also be reverted individually. There is no database migration to reverse.
