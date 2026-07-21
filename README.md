# 🧾 Receipts

A private, local archive for tracking history about people, places, events, and projects. Upload screenshots, texts, links, videos — AI reads them, figures out *when they actually happened*, and makes everything searchable with plain questions like *"Have Laura and I ever talked about going to Brewskys?"*

Everything is stored on your computer. Nothing is uploaded anywhere except individual items sent to the AI for analysis (and you can run without AI at all).

## Start it

**Linux (recommended):** run `bash install-launcher.sh` once — this puts 🧾 Receipts in your app menu. From then on, click it like any app: it starts the server and opens your browser (or just opens the browser if it's already running). If you move this folder, run the installer again.

**Any OS, manually:** double-click `start.sh` (Mac/Linux) or `start.bat` (Windows). The browser opens automatically.

The first run installs dependencies (needs Python 3 — free from python.org).

## Turn on the AI

Click **Settings & AI** (bottom-left) and paste an Anthropic API key (get one at console.anthropic.com). Without a key the app still works — uploads, modules, timelines, and keyword search — you just lose AI analysis and question-answering.

Designed to swap to a local model later: the AI layer is one small section in `app.py` (`call_claude`) — point it at a local server (e.g. Ollama) when you have the compute.

## How to use it

1. **Create a module** — a folder for a person, event, place, or project. Presets give you context fields (e.g. for a person: relationship, how you met). The AI reads these fields when searching.
2. **Upload receipts** — screenshots, photos, videos, links, notes. Optionally add context ("texts between me and Laura from March") and/or a manual date.
3. **The AI timestamps each item** using this priority:
   - **Manual date you set** — always wins
   - **Date visible in the content** (a tweet showing "Mar 3, 2017"; "12h ago" computed against the screenshot's capture time)
   - **File metadata** (EXIF capture time)
   - **Upload time** — last resort
   Every record shows a colored badge telling you which source was used, and you can fix any date from the record's detail view.
4. **Search** — from Home (searches everything) or inside a module. Ask real questions; you get an answer, the records that directly match, and a *"you were looking for that, but there's also this"* section of related records.
5. **Timelines** — every module has one, plus a global timeline on Home.

## Where your data lives

Everything is in the `receipts-data/` folder next to the app:

- `files/` — your raw uploads, untouched
- `receipts.db` — all metadata, timestamps, AI analysis, search index
- `config.json` — your settings and API key

- `backups/` — automatic daily copies of the database (last 14 kept)

**Back up or move the whole app by copying this one folder.** Delete `receipts-data` and you start fresh. You can also point the data folder anywhere (like a NAS mount) by setting the `RECEIPTS_DATA` environment variable before launch.

## Built to last

This app is designed so future updates can't destroy your archive: your data lives entirely in `receipts-data/`, separate from the code; raw files are never modified after upload; database changes only ever *add* — nothing is dropped or rewritten; every edit to any record (by you or the AI) is logged in an append-only history (📜 History button on any record), and deletions preserve a snapshot. `CLAUDE.md` in this folder is a binding instruction file for any future AI session that edits this project — it enforces these rules and carries the roadmap (cross-module linking, local models, NAS storage).

## Notes

- Videos/audio/PDFs are stored and timestamped (manual or upload time) but not yet auto-analyzed — add context text so search can find them, or use "Re-analyze" later as the app grows.
- If an upload's AI analysis fails (bad connection, etc.), the file is still saved — open it and hit **Re-analyze**.
- The app runs only on your machine (localhost); nobody else on your network can see it.
