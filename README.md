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

Everything is in one folder, kept **outside the app** so that updating,
reinstalling or deleting Receipts can never touch it:

| Your system | Where the archive lives |
|---|---|
| macOS | `~/Library/Application Support/Receipts` |
| Windows | `%LOCALAPPDATA%\Receipts` |
| Linux | `~/.local/share/receipts` |

Settings shows you the exact path on your machine. Inside it:

- `files/` — your raw uploads, untouched
- `receipts.db` — all metadata, timestamps, AI analysis, search index
- `config.json` — your settings and API key
- `backups/` — automatic daily copies of the database (last 14 kept), plus a
  permanent `snapshot-*.db` taken before any change to the database format

**Back up or move your whole archive by copying that one folder.** Delete it and
you start fresh. You can also point it anywhere (a NAS mount, an external drive)
by setting the `RECEIPTS_DATA` environment variable before launch.

Upgrading from an older version that kept a `receipts-data/` folder next to the
app? Receipts moves it for you on first launch, and deliberately leaves the
original where it was as a safety net.

## Built to last

This app is designed so future updates can't destroy your archive:

- Your data lives outside the application entirely, so replacing the app can't
  reach it.
- Raw files are never modified after upload.
- Database changes are **additive only** — nothing is dropped or rewritten — and
  they run in a transaction, so a failed update rolls back and leaves your
  archive exactly as it was.
- A permanent backup is taken immediately before any database format change, and
  is never pruned.
- Receipts refuses to open an archive written by a *newer* version rather than
  risk writing bad data into it.
- Every edit to any record (by you or the AI) is logged in an append-only
  history (📜 History on any record), and deletions preserve a snapshot.
- **Export everything** in Settings gives you a zip with the database and every
  original file, at any time, for any reason.

Those guarantees are enforced by a test suite (`tests/`) that runs on macOS,
Windows and Linux on every change: it opens archives saved in each historical
format and asserts that not one row is lost, altered or reordered.

`CLAUDE.md` is a binding instruction file for any future AI session that edits
this project — it enforces these rules and carries the roadmap (cross-module
linking, local models, NAS storage).

## Notes

- Videos/audio/PDFs are stored and timestamped (manual or upload time) but not yet auto-analyzed — add context text so search can find them, or use "Re-analyze" later as the app grows.
- If an upload's AI analysis fails (bad connection, etc.), the file is still saved — open it and hit **Re-analyze**.
- The app runs only on your machine (localhost); nobody else on your network can see it.
