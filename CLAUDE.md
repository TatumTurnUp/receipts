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
  (AI cross-record context updates w/ feedback), `change_log` (audit trail,
  carries `module_id` + `entity_label` so entries survive record deletion).
- Naming convention the owner chose — use it everywhere, don't invent new terms:
  "System Audit Log" (all changes, sidebar page), "Module Audit Log" (floating
  widget in module view), "File Audit Log" (per-record modal). All three read
  from `change_log` via `/api/audit` and `/api/records/{id}/history`.
- Timestamp priority: manual > AI-from-content > EXIF metadata > upload time.
  `ts_source`/`ts_confidence`/`ts_reasoning` explain every date.
- AI layer is intentionally thin: `call_claude()` in app.py is the ONLY place
  that talks to a model. Anthropic API today.

## Owner's roadmap (context for future sessions)

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
- UI ideas noted: per-module "brings me joy" toggle example — any such feature
  must be a new column with a default, per Rule 2.

## Feature-change etiquette

Even for a "major UI overhaul": the UI is a lens over the archive, never the
archive itself. Rebuild `static/index.html` freely, but every existing record,
module, timestamp, amendment, and history entry must render and remain editable
afterward. If a feature can't be built without violating the Sacred Rules,
propose an alternative to the owner instead of bending them.
