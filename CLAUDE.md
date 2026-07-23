# Receipts — instructions for any AI/developer touching this project

Read this before editing anything. The owner is a media preservationist. This app
holds their irreplaceable personal archive. Convenience never outranks preservation.

## The Sacred Rules (non-negotiable)

1. **Never touch `receipts-data/`.** That folder is the archive: raw uploads in
   `files/` (never modified after write — originals are sacred), `receipts.db`
   (all metadata/history), `config.json`, `backups/`. App code may read/write it
   at runtime; you as a developer never restructure, migrate-in-place, rename,
   or "clean up" anything inside it.
2. **Database changes are ADDITIVE ONLY.** New tables or new columns with
   defaults, registered in the `MIGRATIONS` dict in `app.py` with a
   `SCHEMA_VERSION` bump. Never `DROP`, never rewrite rows in bulk, never change
   a column's meaning. Old data must remain readable forever.
3. **Every mutation is audited.** Any code path that changes a record or module
   must call `log_change(...)`. The `change_log` table is append-only — never
   delete from it. Deletions log a content snapshot before removing the row.
4. **Don't break API compatibility casually.** The frontend and backend ship
   together, but response fields should be added, not renamed/removed, so older
   data and any future exports keep working.
5. **Test against a scratch data dir** (`RECEIPTS_DATA=/tmp/... python3 app.py`),
   never against the real archive. Verify: startup with an EXISTING old
   database, upload, search, timeline, history — before delivering changes.
6. **When in doubt, back up first.** `backup_db()` keeps daily copies in
   `receipts-data/backups/` (last 14). Big/risky change? Tell the owner to copy
   `receipts-data/` somewhere safe before running the new version.

## Architecture (current)

- Single-file FastAPI backend (`app.py`), single-file vanilla-JS frontend
  (`static/index.html`), SQLite + FTS5, storage on local disk.
- Tables: `modules`, `records`, `records_fts` (+triggers), `amendments`
  (AI cross-record context updates; feedback semantics the owner chose:
  👍 up = keep the change + remember as correct; 😐 neutral = revert but do NOT
  count against the AI; 👎 down = revert + remember as a mistake. Approved
  amendments lose the highlight but keep the dashed underline + hover tooltip),
  `change_log` (audit trail,
  carries `module_id` + `entity_label` so entries survive record deletion).
- Naming convention the owner chose — use it everywhere, don't invent new terms:
  "System Audit Log" (all changes, sidebar page), "Module Audit Log" (floating
  widget in module view), "File Audit Log" (per-record modal). All three read
  from `change_log` via `/api/audit` and `/api/records/{id}/history`.
- Timestamp priority: manual > AI-from-content > EXIF metadata > upload time.
  `ts_source`/`ts_score`/`ts_reasoning` explain every date. `ts_score` is the
  owner's 1-10 confidence scale: 10 = exact date visible in content (manual = 10),
  2-9 = AI inference from context clues (colors: 9-10 green, 6-8 yellow, 1-5 red),
  1 = metadata/upload fallback with zero content evidence — always flagged red.
  Hour/minute only when evidenced; midnight means date-only. Multiple visible
  timestamps -> earliest wins. `ts_confidence` (exact/approximate/guess) is
  legacy — keep it populated for compatibility, but ts_score is the truth.
- Timeline sorting: module timelines sort by content date or upload date
  (`created_at`); both dates always shown (primary large, secondary faint).
- Dating is optional: `ts_source='none'` + NULL `ts_effective` means the owner
  opted out (spec sheets etc.) — no score chip, timeline placement falls back
  to upload date. Record kinds: image|video|audio|file|note|link|moment.
  Notes (yellow), links (blue), moments (orange) are tinted in timeline/cards;
  links carry og: preview data in `link_meta`. PDFs and text files are analyzed
  (document blocks / inline text), not just images.
- AI layer is intentionally thin: `call_claude()` in app.py is the ONLY place
  that talks to a model. Anthropic API today.
- Efficiency layer (don't undo these): system prompts use prompt caching
  (`cache_control: ephemeral`); images are downscaled locally to ≤1568px JPEG
  before sending (originals untouched); PDFs over
  `pdf_document_block_max_pages` (config, default 20) fall back to extracted
  text instead of document blocks; the amendment pass only runs when analysis
  returns `cross_update_hint != false`; token usage accumulates in config.json
  `usage` and shows in Settings.

## Owner's roadmap (context for future sessions)

- **Cross-module timestamp corroboration:** ts_score inference currently uses
  sibling records within the same module as evidence. When module linking lands,
  extend the evidence pool across linked modules.
- **Global Timeline workspace:** the sidebar "Global Timeline" entry is a
  work-in-progress placeholder. The owner's vision: an explorable canvas —
  pan time on X, modules on Y, zoom from years to minutes, records visually
  linked across the archive. The simple list version stays in Home's tab.
- **Module hopping / cross-links:** when a new module is created (e.g. a place),
  scan other modules' records for references; suggest them with approve/deny;
  approved records appear in both modules with a "Shared from [origin]"
  indicator linking back. Same suggestion flow for future uploads.
- **Local models:** swap `call_claude()` to a local endpoint (e.g. Ollama) when
  the owner has compute. Keep the function signature; add a provider switch in
  config.
- **NAS storage:** raw files (and possibly the whole data dir) will move to a
  NAS. `RECEIPTS_DATA` env var already relocates the data dir; a config-based
  storage path with a safe, verified copy-migration (copy, verify, then let the
  owner delete the old copy manually) is the intended approach. Never move-and-
  delete automatically.
- Model usage fallback (auto-downgrade to cheaper model at high usage) — owner
  mentioned, low priority.
- **Custom LLM instructions:** owner wants to explore a client-side setting for
  global custom AI instructions (style/voice preferences), and possibly
  per-module instructions/context on top. Note: description voice + extracted-
  text-as-search-index rules currently live in ANALYZE_SYSTEM in app.py; a
  future custom-instructions setting should append to those, not replace them.
- UI ideas noted: per-module "brings me joy" toggle example — any such feature
  must be a new column with a default, per Rule 2.

## Feature-change etiquette

Even for a "major UI overhaul": the UI is a lens over the archive, never the
archive itself. Rebuild `static/index.html` freely, but every existing record,
module, timestamp, amendment, and history entry must render and remain editable
afterward. If a feature can't be built without violating the Sacred Rules,
propose an alternative to the owner instead of bending them.
