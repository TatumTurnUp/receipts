"""
Receipts — a local, private archive for tracking history about people, places,
events, and projects. Upload texts, screenshots, links, videos; AI extracts
context and timestamps; everything is searchable and lands on a timeline.

All data stays on your machine in the ./receipts-data folder.
"""

import base64
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests as http
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------- paths / db

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("RECEIPTS_DATA", ROOT / "receipts-data"))
FILES = DATA / "files"
DB_PATH = DATA / "receipts.db"
CONFIG_PATH = DATA / "config.json"

DATA.mkdir(parents=True, exist_ok=True)
FILES.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "anthropic_api_key": "",
    "model": "claude-sonnet-5",
    "max_ask_records": 60,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --- preservation layer -----------------------------------------------------
# SCHEMA_VERSION bumps whenever the database shape changes. Migrations are
# ADDITIVE ONLY (new tables / new columns with defaults) — never drop or
# rewrite existing data. A dated backup of the DB is kept in
# receipts-data/backups/ (one per day, last 14 kept) so no update can
# silently destroy history.

SCHEMA_VERSION = 6

MIGRATIONS: dict = {
    # v4: audit entries remember their module and a human label, so the
    # Module Audit Log stays meaningful even after a record is deleted.
    # The UPDATEs only backfill the new (empty) columns from existing data.
    4: [
        "ALTER TABLE change_log ADD COLUMN module_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE change_log ADD COLUMN entity_label TEXT NOT NULL DEFAULT ''",
        "UPDATE change_log SET module_id=COALESCE((SELECT r.module_id FROM records r "
        "WHERE r.id=change_log.entity_id),'') WHERE entity_type='record' AND module_id=''",
        "UPDATE change_log SET module_id=entity_id WHERE entity_type='module' AND module_id=''",
    ],
    # v5: numeric timestamp confidence (1-10). Backfill maps old text confidence.
    5: [
        "ALTER TABLE records ADD COLUMN ts_score INTEGER NOT NULL DEFAULT 0",
        "UPDATE records SET ts_score = CASE "
        "WHEN ts_source='manual' THEN 10 "
        "WHEN ts_source='content' AND ts_confidence='exact' THEN 10 "
        "WHEN ts_source='content' THEN 7 "
        "ELSE 1 END WHERE ts_score=0",
    ],
    # v6: link previews (og: metadata) for link records.
    # Dateless records use ts_effective=NULL + ts_source='none' — no migration needed.
    6: [
        "ALTER TABLE records ADD COLUMN link_meta TEXT NOT NULL DEFAULT ''",
    ],
    # future example:
    # 7: ["ALTER TABLE modules ADD COLUMN brings_joy INTEGER NOT NULL DEFAULT 0"],
}


def backup_db():
    if not DB_PATH.exists():
        return
    bdir = DATA / "backups"
    bdir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    existing = sorted(bdir.glob("receipts-*.db"))
    if any(today in b.name for b in existing):
        return
    shutil.copy2(DB_PATH, bdir / f"receipts-{today}.db")
    for old in existing[:-13]:
        try:
            old.unlink()
        except Exception:
            pass


def migrate(conn: sqlite3.Connection):
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    for target in range(v + 1, SCHEMA_VERSION + 1):
        for sql in MIGRATIONS.get(target, []):
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'generic',  -- person|event|place|project|generic
            fields_json TEXT NOT NULL DEFAULT '{}',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,               -- image|video|audio|link|note|file
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',    -- note text, link url, extracted text
            description TEXT NOT NULL DEFAULT '',  -- AI description
            user_context TEXT NOT NULL DEFAULT '', -- context the user typed at upload
            file_name TEXT,                   -- stored filename in receipts-data/files
            original_name TEXT,
            mime TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            ts_effective TEXT,                -- ISO timestamp used on the timeline
            ts_source TEXT NOT NULL DEFAULT 'upload',  -- manual|content|metadata|upload
            ts_confidence TEXT NOT NULL DEFAULT '',    -- exact|approximate|guess (legacy)
            ts_score INTEGER NOT NULL DEFAULT 0,       -- 1-10 confidence scale
            ts_reasoning TEXT NOT NULL DEFAULT '',
            link_meta TEXT NOT NULL DEFAULT '',        -- og: preview data for links
            ai_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS change_log (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,   -- record|module
            entity_id TEXT NOT NULL,
            field TEXT NOT NULL,         -- created|deleted|title|description|body|tags|timestamp|...
            old_value TEXT NOT NULL DEFAULT '',
            new_value TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL DEFAULT 'you',  -- you|ai|system
            note TEXT NOT NULL DEFAULT '',
            module_id TEXT NOT NULL DEFAULT '',
            entity_label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS amendments (
            id TEXT PRIMARY KEY,
            target_record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
            source_record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
            added_text TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            old_description TEXT NOT NULL DEFAULT '',
            new_description TEXT NOT NULL DEFAULT '',
            verdict TEXT NOT NULL DEFAULT '',      -- ''|up|neutral|down
            status TEXT NOT NULL DEFAULT 'active', -- active|reversed
            created_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
            title, body, description, tags, user_context,
            content='records', content_rowid='rowid'
        );

        CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
            INSERT INTO records_fts(rowid, title, body, description, tags, user_context)
            VALUES (new.rowid, new.title, new.body, new.description, new.tags_json, new.user_context);
        END;
        CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
            INSERT INTO records_fts(records_fts, rowid, title, body, description, tags, user_context)
            VALUES ('delete', old.rowid, old.title, old.body, old.description, old.tags_json, old.user_context);
        END;
        CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
            INSERT INTO records_fts(records_fts, rowid, title, body, description, tags, user_context)
            VALUES ('delete', old.rowid, old.title, old.body, old.description, old.tags_json, old.user_context);
            INSERT INTO records_fts(rowid, title, body, description, tags, user_context)
            VALUES (new.rowid, new.title, new.body, new.description, new.tags_json, new.user_context);
        END;
        """
    )
    migrate(conn)
    conn.commit()
    conn.close()


backup_db()
init_db()

# ------------------------------------------------------------------ helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def row_to_record(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d.pop("tags_json") or "[]")
    d["ai"] = json.loads(d.pop("ai_json") or "{}")
    try:
        d["link_meta"] = json.loads(d.get("link_meta") or "{}")
    except Exception:
        d["link_meta"] = {}
    return d


def log_change(entity_type: str, entity_id: str, field: str,
               old: str = "", new: str = "", actor: str = "you", note: str = "",
               module_id: str = "", label: str = ""):
    """Append-only audit trail. Nothing in the archive changes without a trace."""
    try:
        conn = db()
        conn.execute(
            """INSERT INTO change_log (id,entity_type,entity_id,field,old_value,new_value,
               actor,note,module_id,entity_label,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (new_id(), entity_type, entity_id, field,
             str(old or "")[:2000], str(new or "")[:2000], actor, note,
             module_id, str(label or "")[:120], now_iso()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_label(rec: dict) -> str:
    return rec.get("title") or rec.get("original_name") or (rec.get("body") or "")[:60] or "Untitled"


def kind_for_mime(mime: str) -> str:
    if not mime:
        return "file"
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("text/") or mime in ("application/pdf",):
        return "file"
    return "file"


def exif_datetime(path: Path) -> Optional[str]:
    """Best-effort capture time from image EXIF."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        img = Image.open(path)
        exif = img.getexif()
        if not exif:
            return None
        by_name = {TAGS.get(k, k): v for k, v in exif.items()}
        # also check the Exif sub-IFD for DateTimeOriginal
        try:
            sub = exif.get_ifd(0x8769)
            for k, v in sub.items():
                by_name[TAGS.get(k, k)] = v
        except Exception:
            pass
        for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            v = by_name.get(key)
            if v:
                v = str(v).strip()
                m = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", v)
                if m:
                    return "{}-{}-{}T{}:{}:{}".format(*m.groups())
        return None
    except Exception:
        return None


def fetch_link_meta(url: str) -> dict:
    """Best-effort og: metadata for link previews (like Twitter link cards)."""
    try:
        resp = http.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0 (Receipts local archive)"})
        html = resp.text[:300_000]

        def og(prop):
            m = re.search(
                r'<meta[^>]+(?:property|name)=["\']' + prop + r'["\'][^>]+content=["\']([^"\']+)["\']',
                html, re.I) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + prop + r'["\']',
                html, re.I)
            return m.group(1).strip() if m else ""

        title = og("og:title") or og("twitter:title")
        if not title:
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = m.group(1).strip()[:150] if m else ""
        meta = {
            "title": title[:200],
            "description": (og("og:description") or og("twitter:description") or og("description"))[:300],
            "image": og("og:image") or og("twitter:image"),
            "site": og("og:site_name") or re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0]),
        }
        return {k: v for k, v in meta.items() if v}
    except Exception:
        return {}


ANALYZABLE_TEXT_MIMES = ("text/plain", "text/markdown", "text/csv", "text/html")


def is_analyzable(kind: str, mime: str) -> bool:
    return (kind in ("image", "note", "link", "moment")
            or mime == "application/pdf"
            or (mime or "") in ANALYZABLE_TEXT_MIMES)


def file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


# ------------------------------------------------------------------ AI layer

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def ai_available() -> bool:
    return bool(load_config().get("anthropic_api_key"))


def call_claude(system: str, user_content, max_tokens: int = 1500, timeout: int = 120) -> str:
    cfg = load_config()
    key = cfg.get("anthropic_api_key")
    if not key:
        raise RuntimeError("No API key configured")
    resp = http.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": cfg.get("model", DEFAULT_CONFIG["model"]),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Anthropic API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []))


def parse_json_block(text: str) -> dict:
    """Extract the first JSON object from a model reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    in_str = False
    esc_next = False
    for i in range(start, len(text)):
        c = text[i]
        if esc_next:
            esc_next = False
            continue
        if c == "\\":
            esc_next = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        return {}
    # reply was truncated mid-object — repair by closing open string/braces
    candidate = text[start:].rstrip()
    candidate = re.sub(r",\s*\"[^\"]*$", "", candidate)  # drop a half-written key
    if in_str and candidate.count('"') % 2 == 1:
        candidate += '"'
    try:
        return json.loads(candidate + "}" * max(depth, 1))
    except Exception:
        return {}


ANALYZE_SYSTEM = """You are the ingestion engine for someone's personal receipts archive.
You are given an uploaded item (an image, or text) plus file metadata, the module it was
filed under, and user-provided context.

VOICE — very important:
- The archive owner is the person reading everything you write. Write descriptions in
  second person: "you", "your". NEVER say "the user", "the owner", or "the uploader".
  Example: "You joke about bringing a date twice your age to Laura's wedding."
- The module tells you who or what this is about. Refer to them naturally by name.
  If the module is a person named Laura, write "Laura", never "a contact named Laura".
- Ignore incidental app UI chrome: location text under a contact's name in a messaging
  app (that's just location sharing), battery/signal icons, keyboards, read receipts.
  Do not mention them in the description.
- Use correct product names and casing: iMessage, iPhone, X/Twitter, TikTok.
- If existing record titles are provided, match their style, length, and format so the
  module looks consistent.

Your job:
1. Describe what the item is.
   DESCRIPTION STYLE: natural, conversational prose — the way you'd explain the item
   to a friend, not a spec sheet. Weave in the facts that matter (counts, weights,
   dimensions, names, models) but humanize them: round numbers sensibly, convert units
   to readable ones (12192 mm -> "about 12.2 m"), skip tolerances, interface codes,
   and part-number soup unless they're the whole point. GOOD: "The H40 Plus holds 420
   shoebox miners (S19/S21/S23 Hydro series), ships at about 10 tons and runs at
   18.6 tons, and measures roughly 12.2 by 2.4 by 2.9 meters. The dry cooling tower
   is a separate unit." BAD: "420 miners, 2400 kW, PUE 1.03 @15°C, AC400V ±5%
   50/60Hz, DN125 x 4, 200 m³/h."
   EXTRACTED_TEXT is a SEARCH INDEX, never shown to the owner. For short items
   (screenshots, messages, tweets) transcribe the text fully. For long documents,
   do NOT transcribe — output a compact index of searchable terms: names, model
   numbers, key specs and figures, distinctive phrases, section topics. Max ~600 words.
2. Determine the best timestamp for WHEN THE CONTENT HAPPENED (not when it was uploaded),
   and score your confidence on a strict 1-10 scale. The score measures HOW DIRECTLY
   the date is evidenced — not how hard you worked for it:
   - 10: the date is stated outright by a primary source: an exact, complete date visible
     in the content (a tweet showing "Mar 3, 2017", a header "Thu, Jul 16"), OR the
     owner's context note states the date explicitly ("these are from July 2nd") AND
     at least one other signal is consistent (visible times, metadata, referenced events).
   - 9: the date is stated outright by exactly one source with nothing to corroborate it:
     the owner's context note alone, or a visible date with one small part (like the year)
     resolved by solid inference.
   - 6-8: the date is COMPUTED from indirect clues: relative times in content ("12h ago")
     against capture metadata; relative phrases in the owner's note ("last Thursday" —
     resolve against the upload date); references to datable events; corroboration from
     the other records of this module provided below. More independent clues -> higher.
   - 2-5: weak inference — rough era/season guesses from soft context.
   - 1: NO usable evidence at all; falling back to file metadata (EXIF) or upload time.
     Set source "metadata" or "upload". This is a flagged, untrusted date.
   The owner's context note is direct testimony from the person who was there — treat a
   date it states as fact (9-10), not as a clue to be discounted.
   Rules:
   - HOUR AND MINUTE ONLY IF EVIDENCED. If the content shows a time, include it.
     Otherwise return midnight (T00:00:00) — the UI treats midnight as date-only.
     Never invent a time of day.
   - MULTIPLE timestamps visible (e.g. a Slack or iMessage thread spanning times):
     use the EARLIEST date and time mentioned.
   - The user's context note is an authoritative hint. Resolve its relative phrases
     ("today", "yesterday", "last Thursday", "last month") against the upload time
     given in the metadata — NOT against dates inside the content.
   - Corroborating records from this module may pin down otherwise vague dates
     (overlapping conversations, same events). Cite them in your reasoning if used.
3. Suggest a short title, tags, and any people/places/entities mentioned.

Reply with ONLY a JSON object. EVERY field below is REQUIRED — never omit any of them.
timestamp_score is the most important field in this system; if timestamp is not null,
timestamp_score MUST be an integer 1-10 (if timestamp is null, use 1):
{
 "timestamp": str|null (ISO 8601, e.g. "2017-03-03T00:00:00"),
 "timestamp_score": int,
 "timestamp_source": "content"|"metadata"|"upload",
 "timestamp_reasoning": str,
 "title": str, "description": str, "extracted_text": str,
 "tags": [str], "entities": [str]
}"""

SCORE_FOLLOWUP_SYSTEM = """You scored nothing yet. Given how an archive item's date was
determined, output its confidence score on this scale:
10 = date stated by a primary source (visible in content, or the owner's context note
     states it AND another signal corroborates); 9 = stated by one source, uncorroborated;
6-8 = computed from indirect clues (relative times vs metadata, datable events,
     sibling records); 2-5 = weak inference; 1 = metadata/upload fallback only.
Reply ONLY with JSON: {"timestamp_score": int}"""


def score_followup(result: dict, user_context: str) -> int:
    """The model omitted timestamp_score — ask it to score its own reasoning."""
    payload = (f"Timestamp: {result.get('timestamp')}\n"
               f"Source: {result.get('timestamp_source')}\n"
               f"Owner's context note: {user_context or '(none)'}\n"
               f"Dating reasoning: {result.get('timestamp_reasoning','')}")
    raw = call_claude(SCORE_FOLLOWUP_SYSTEM, [{"type": "text", "text": payload}], max_tokens=100)
    return max(1, min(10, int(parse_json_block(raw).get("timestamp_score"))))


def get_module_row(mid: str) -> Optional[dict]:
    conn = db()
    r = conn.execute("SELECT * FROM modules WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["fields"] = json.loads(d.pop("fields_json") or "{}")
    return d


def module_context_lines(module: Optional[dict]) -> list:
    if not module:
        return []
    lines = [f"Filed under module: \"{module['name']}\" (type: {module['type']})"]
    for k, v in (module.get("fields") or {}).items():
        if v:
            lines.append(f"  {k}: {v}")
    if module.get("notes"):
        lines.append(f"  Owner's notes about this module: {module['notes']}")
    return lines


def sibling_titles(module_id: str, exclude_id: str, limit: int = 5) -> list:
    conn = db()
    rows = conn.execute(
        """SELECT title FROM records WHERE module_id=? AND id!=? AND title!=''
           ORDER BY created_at DESC LIMIT ?""",
        (module_id, exclude_id, limit),
    ).fetchall()
    conn.close()
    return [r["title"] for r in rows]


def sibling_evidence(module_id: str, exclude_id: str, limit: int = 8) -> list:
    """Recent records in the module, as corroborating evidence for dating new uploads."""
    conn = db()
    rows = conn.execute(
        """SELECT title, ts_effective, ts_score, body FROM records
           WHERE module_id=? AND id!=? ORDER BY created_at DESC LIMIT ?""",
        (module_id, exclude_id, limit),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append(f'- "{r["title"] or "Untitled"}" (dated {r["ts_effective"] or "unknown"}, '
                   f'confidence {r["ts_score"] or "?"}/10): {(r["body"] or "")[:150]}')
    return out


def analyze_record(record: dict, file_path: Optional[Path]) -> dict:
    """Run AI analysis. Returns the parsed JSON result (may be empty)."""
    module = get_module_row(record["module_id"])
    meta_lines = [f"Uploaded at: {record['created_at']} (this is 'now' for the user's context note)"]
    meta_lines += module_context_lines(module)
    titles = sibling_titles(record["module_id"], record["id"])
    if titles:
        meta_lines.append("Existing record titles in this module (match their style): "
                          + "; ".join(f'"{t}"' for t in titles))
    evidence = sibling_evidence(record["module_id"], record["id"])
    if evidence:
        meta_lines.append("Other records in this module (corroborating evidence for dating):")
        meta_lines += evidence
    if file_path and file_path.exists():
        meta_lines.append(f"File name: {record.get('original_name') or file_path.name}")
        ex = exif_datetime(file_path)
        if ex:
            meta_lines.append(f"EXIF capture time: {ex}")
        meta_lines.append(f"File modified time: {file_mtime_iso(file_path)}")
    if record.get("user_context"):
        meta_lines.append(f"User-provided context: {record['user_context']}")
    if record.get("body") and record["kind"] in ("note", "link"):
        meta_lines.append(f"Content: {record['body']}")
    meta = "\n".join(meta_lines)

    content = []
    mime = record.get("mime") or ""
    if file_path and file_path.exists():
        size = file_path.stat().st_size
        if record["kind"] == "image" and size <= 4_500_000:
            b64 = base64.b64encode(file_path.read_bytes()).decode()
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime or "image/png", "data": b64},
            })
        elif mime == "application/pdf":
            # The API caps PDFs (~100 pages / size). Send the raw document when it
            # fits; otherwise fall back to locally extracted text.
            pages = None
            try:
                from pypdf import PdfReader
                pages = len(PdfReader(str(file_path)).pages)
            except Exception:
                pass
            if size <= 15_000_000 and (pages is None or pages <= 90):
                b64 = base64.b64encode(file_path.read_bytes()).decode()
                content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
                })
            else:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(file_path))
                    text = "\n".join((p.extract_text() or "") for p in reader.pages[:150])
                    meta += (f"\n\nThis PDF is too large to attach ({pages} pages). "
                             f"Extracted text (first 150 pages):\n" + text[:30_000])
                except Exception as e:
                    meta += f"\n\n(PDF too large to attach and text extraction failed: {e})"
        elif mime in ANALYZABLE_TEXT_MIMES and size <= 2_000_000:
            try:
                meta += "\n\nFile contents:\n" + file_path.read_text(errors="replace")[:20_000]
            except Exception:
                pass
    if record.get("ts_source") == "none":
        meta += ("\n\nNOTE: the owner opted OUT of dating this item. Skip timestamp work: "
                 "return timestamp null, timestamp_score 1, timestamp_reasoning \"Dating opted out.\" "
                 "Focus on the description, extracted text, and tags.")
    content.append({"type": "text", "text": f"Item metadata:\n{meta}\n\nAnalyze this item."})

    raw = call_claude(ANALYZE_SYSTEM, content, max_tokens=8000, timeout=300)
    result = parse_json_block(raw)
    if not result:
        raise RuntimeError(f"AI returned unparseable output: {raw[:200]}")
    return result


def persist_ai_error(record_id: str, error: str):
    """Store an analysis failure on the record so it's visible, not just a toast."""
    try:
        conn = db()
        # record the failure without clobbering a previous successful analysis
        conn.execute("""UPDATE records SET ai_json=? WHERE id=?
                        AND (ai_json='{}' OR ai_json LIKE '{"error%')""",
                     (json.dumps({"error": error[:500]}), record_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def apply_analysis(record_id: str, result: dict, manual_ts: Optional[str]):
    """Merge AI results into the record, respecting timestamp priority."""
    if not result:
        return
    conn = db()
    r = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    if not r:
        conn.close()
        return
    sets, vals = [], []

    def set_col(col, val):
        sets.append(f"{col}=?")
        vals.append(val)

    if result.get("title") and not r["title"]:
        set_col("title", result["title"][:200])
    if result.get("description"):
        set_col("description", result["description"])
    if result.get("extracted_text") and (r["kind"] == "image" or (r["kind"] == "file" and not r["body"])):
        set_col("body", result["extracted_text"])
    if result.get("tags"):
        set_col("tags_json", json.dumps(result["tags"][:15]))
    set_col("ai_json", json.dumps(result))

    # timestamp priority: manual > AI(content) > AI(metadata) > upload
    # dateless records (ts_source='none') never get a timestamp from analysis
    if not manual_ts and r["ts_source"] not in ("manual", "none"):
        ts = result.get("timestamp")
        src = result.get("timestamp_source", "upload")
        try:
            score = max(1, min(10, int(result.get("timestamp_score"))))
        except Exception:
            # model omitted the numeric score — ask it to score its own reasoning
            try:
                score = score_followup(result, r["user_context"])
                result["timestamp_score"] = score  # keep ai_json truthful
            except Exception:
                conf = result.get("timestamp_confidence", "")
                score = {"exact": 9, "approximate": 7}.get(conf, 6 if src == "content" else 1)
        if src in ("metadata", "upload"):
            score = 1
        if ts and src in ("content", "metadata"):
            set_col("ts_effective", ts)
            set_col("ts_source", src)
            set_col("ts_score", score)
            set_col("ts_confidence", "exact" if score >= 9 else "approximate" if score >= 6 else "guess")
            set_col("ts_reasoning", result.get("timestamp_reasoning", ""))
        elif result.get("timestamp_reasoning"):
            # AI found nothing usable — record stays on metadata/upload date, flagged
            set_col("ts_score", 1)
            set_col("ts_reasoning", result.get("timestamp_reasoning", ""))

    if sets:
        vals.append(record_id)
        conn.execute(f"UPDATE records SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    lbl = result.get("title") or r["title"] or r["original_name"] or "Untitled"
    if result.get("description") and result["description"] != r["description"]:
        log_change("record", record_id, "description", r["description"],
                   result["description"], actor="ai", note="AI analysis",
                   module_id=r["module_id"], label=lbl)
    if result.get("timestamp"):
        log_change("record", record_id, "timestamp", r["ts_effective"],
                   f'{result["timestamp"]} ({result.get("timestamp_source","")})',
                   actor="ai", note=result.get("timestamp_reasoning", ""),
                   module_id=r["module_id"], label=lbl)


# -------------------------------------------------------------- amendments

AMEND_SYSTEM = """You maintain someone's personal receipts archive. A new record was just
added to a module. You get the new record plus the earlier records in the same module.

Decide whether the new record REVEALS information that meaningfully adds context to, or
corrects, any earlier record's description. Example: an earlier record says "You joke
about bringing a date twice your age to Laura's wedding" and the new record reveals Laura
and Cooper broke up -> update it to "...to Laura's wedding with Cooper, when they were
still together."

Rules:
- Be conservative. Only clear, meaningful revelations. Most uploads change nothing.
- Write in second person ("you"), matching the existing description's voice.
- new_description must be the FULL replacement description. added_text must be the exact
  new phrase you inserted (an exact substring of new_description).
- reason: one sentence, plain language, saying what the new item revealed.

Reply ONLY with JSON: {"updates": [{"record_id": str, "new_description": str,
"added_text": str, "reason": str}]}   (empty list if nothing changes)"""


def run_amendment_pass(new_rid: str) -> int:
    """Check if a new record updates context of earlier records in its module."""
    rec = get_record(new_rid)
    conn = db()
    others = [row_to_record(r) for r in conn.execute(
        """SELECT * FROM records WHERE module_id=? AND id!=? AND description!=''
           ORDER BY created_at DESC LIMIT 40""", (rec["module_id"], new_rid))]
    fb = conn.execute(
        """SELECT added_text, reason, verdict FROM amendments
           WHERE verdict IN ('up','down') ORDER BY created_at DESC LIMIT 6""").fetchall()
    conn.close()
    if not others:
        return 0

    lines = ["NEW RECORD:", json.dumps({
        "title": rec["title"], "description": rec["description"],
        "text": (rec["body"] or "")[:600], "timestamp": rec["ts_effective"],
    }), "", "EARLIER RECORDS:"]
    for o in others:
        lines.append(json.dumps({
            "record_id": o["id"], "title": o["title"],
            "description": o["description"], "timestamp": o["ts_effective"],
        }))
    if fb:
        lines.append("\nPast feedback on your amendments (learn from this):")
        for f in fb:
            lines.append(f"- You added \"{f['added_text']}\" because {f['reason']} -> user said this was "
                         + ("CORRECT" if f["verdict"] == "up" else "WRONG (it was reverted)"))

    raw = call_claude(AMEND_SYSTEM, [{"type": "text", "text": "\n".join(lines)}], max_tokens=2000)
    result = parse_json_block(raw)
    count = 0
    pending_logs = []
    by_id = {o["id"]: o for o in others}
    conn = db()
    for u in result.get("updates", [])[:5]:
        tid = u.get("record_id")
        nd, at = (u.get("new_description") or "").strip(), (u.get("added_text") or "").strip()
        if tid not in by_id or not nd or not at or at not in nd:
            continue
        old = by_id[tid]["description"]
        conn.execute("UPDATE records SET description=? WHERE id=?", (nd, tid))
        conn.execute(
            """INSERT INTO amendments (id,target_record_id,source_record_id,added_text,
               reason,old_description,new_description,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (new_id(), tid, new_rid, at, u.get("reason", ""), old, nd, now_iso()))
        pending_logs.append((tid, old, nd, u.get("reason", "")))
        count += 1
    conn.commit()
    conn.close()
    for tid, old, nd, reason in pending_logs:
        log_change("record", tid, "description", old, nd, actor="ai",
                   note=f"Amended after a newer upload: {reason}",
                   module_id=rec["module_id"], label=record_label(by_id[tid]))
    return count


def attach_amendments(records: list):
    """Add amendments_target / amendments_source to each record dict."""
    if not records:
        return records
    ids = [r["id"] for r in records]
    ph = ",".join("?" * len(ids))
    conn = db()
    rows = conn.execute(
        f"""SELECT a.*, t.title AS target_title, t.original_name AS target_file,
                   s.title AS source_title, s.original_name AS source_file
            FROM amendments a
            JOIN records t ON t.id = a.target_record_id
            JOIN records s ON s.id = a.source_record_id
            WHERE a.target_record_id IN ({ph}) OR a.source_record_id IN ({ph})""",
        ids + ids).fetchall()
    conn.close()
    amends = [dict(r) for r in rows]
    for r in records:
        r["amendments_target"] = [a for a in amends
                                  if a["target_record_id"] == r["id"] and a["status"] == "active"]
        r["amendments_source"] = [a for a in amends if a["source_record_id"] == r["id"]]
    return records


# ------------------------------------------------------------------- search

def fts_query_terms(q: str) -> str:
    terms = re.findall(r"[A-Za-z0-9']+", q)
    return " OR ".join(t for t in terms if len(t) > 1) or (terms[0] if terms else '""')


def keyword_search(q: str, module_id: Optional[str], limit: int = 100) -> list:
    conn = db()
    try:
        sql = """SELECT r.* FROM records r JOIN records_fts f ON r.rowid = f.rowid
                 WHERE records_fts MATCH ?"""
        args = [fts_query_terms(q)]
        if module_id:
            sql += " AND r.module_id=?"
            args.append(module_id)
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        like = f"%{q}%"
        sql = """SELECT * FROM records WHERE (title LIKE ? OR body LIKE ? OR description LIKE ?)"""
        args = [like, like, like]
        if module_id:
            sql += " AND module_id=?"
            args.append(module_id)
        sql += " LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
    out = attach_amendments([row_to_record(r) for r in rows])
    conn.close()
    return out


ASK_SYSTEM = """You are the search brain of a personal receipts archive.
The user asks a question. You get a list of candidate records (id, module, title,
description, content text, timestamp). Decide which records DIRECTLY answer the
question, and which are RELATED but not a direct answer (same person/place/topic
but different angle) — the "you were looking for this, but there's also this" pile.

Reply with ONLY JSON:
{
 "answer": str (1-3 sentence direct answer to the question, citing what you found; if nothing found, say so),
 "direct": [record ids],
 "related": [{"id": record id, "why": short reason}]
}"""


def ask_ai(question: str, module_id: Optional[str]) -> dict:
    cfg = load_config()
    limit = int(cfg.get("max_ask_records", 60))
    conn = db()
    if module_id:
        total = conn.execute("SELECT COUNT(*) c FROM records WHERE module_id=?", (module_id,)).fetchone()["c"]
    else:
        total = conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
    conn.close()

    if total <= limit:
        conn = db()
        sql = "SELECT * FROM records"
        args = []
        if module_id:
            sql += " WHERE module_id=?"
            args.append(module_id)
        rows = conn.execute(sql, args).fetchall()
        conn.close()
        candidates = [row_to_record(r) for r in rows]
    else:
        # narrow with AI-chosen keywords first
        kw_raw = call_claude(
            "Extract search keywords (names, places, topics, synonyms) from the question. "
            'Reply ONLY with JSON: {"keywords": [str]}',
            [{"type": "text", "text": question}],
            max_tokens=300,
        )
        kws = parse_json_block(kw_raw).get("keywords", []) or [question]
        candidates = keyword_search(" ".join(kws), module_id, limit)

    if not candidates:
        return {"answer": "No records found in scope for this question.", "direct": [], "related": []}

    conn = db()
    mod_names = {m["id"]: m["name"] for m in conn.execute("SELECT id,name FROM modules")}
    conn.close()

    lines = []
    for c in candidates[:limit]:
        lines.append(json.dumps({
            "id": c["id"],
            "module": mod_names.get(c["module_id"], ""),
            "kind": c["kind"],
            "title": c["title"],
            "description": (c["description"] or "")[:300],
            "text": (c["body"] or "")[:500],
            "user_context": (c["user_context"] or "")[:200],
            "timestamp": c["ts_effective"],
        }))
    ctx = ""
    if module_id:
        mod = get_module_row(module_id)
        if mod:
            ctx = "Module context:\n" + "\n".join(module_context_lines(mod)) + "\n\n"
    payload = f"{ctx}Question: {question}\n\nCandidate records:\n" + "\n".join(lines)
    raw = call_claude(ASK_SYSTEM, [{"type": "text", "text": payload}], max_tokens=2000)
    result = parse_json_block(raw)

    by_id = {c["id"]: c for c in candidates}
    direct = [by_id[i] for i in result.get("direct", []) if i in by_id]
    related = []
    for item in result.get("related", []):
        rid = item.get("id") if isinstance(item, dict) else item
        if rid in by_id and by_id[rid] not in direct:
            rec = dict(by_id[rid])
            rec["why_related"] = item.get("why", "") if isinstance(item, dict) else ""
            related.append(rec)
    return {"answer": result.get("answer", ""),
            "direct": attach_amendments(direct), "related": attach_amendments(related)}


# ---------------------------------------------------------------------- app

app = FastAPI(title="Receipts")


class ModuleIn(BaseModel):
    name: str
    type: str = "generic"
    fields: dict = {}
    notes: str = ""


class ModulePatch(BaseModel):
    name: Optional[str] = None
    fields: Optional[dict] = None
    notes: Optional[str] = None


class NoteIn(BaseModel):
    module_id: str
    kind: str = "note"  # note|link|moment
    title: str = ""
    body: str
    user_context: str = ""
    manual_timestamp: Optional[str] = None
    include_date: bool = True


class RecordPatch(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    user_context: Optional[str] = None
    tags: Optional[list] = None
    manual_timestamp: Optional[str] = None  # set/override the timeline timestamp
    clear_manual: Optional[bool] = None


class AskIn(BaseModel):
    question: str
    module_id: Optional[str] = None


class SettingsIn(BaseModel):
    anthropic_api_key: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/health")
def health():
    return {"ok": True, "ai": ai_available()}


@app.post("/api/restart")
def restart():
    """Re-exec the server process so it picks up updated code. Data is untouched."""
    import sys
    import threading

    def _reexec():
        os.environ["RECEIPTS_NO_BROWSER"] = "1"  # don't open a second tab
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Timer(0.6, _reexec).start()
    return {"ok": True}


@app.get("/api/stats")
def stats():
    files_bytes = sum(f.stat().st_size for f in FILES.glob("*") if f.is_file())
    db_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    backups_bytes = sum(f.stat().st_size for f in (DATA / "backups").glob("*.db")) \
        if (DATA / "backups").exists() else 0
    conn = db()
    records = conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
    modules = conn.execute("SELECT COUNT(*) c FROM modules").fetchone()["c"]
    conn.close()
    return {
        "files_bytes": files_bytes,
        "db_bytes": db_bytes,
        "backups_bytes": backups_bytes,
        "total_bytes": files_bytes + db_bytes,
        "records": records,
        "modules": modules,
    }


@app.get("/api/settings")
def get_settings():
    cfg = load_config()
    key = cfg.get("anthropic_api_key", "")
    return {"model": cfg.get("model"), "has_key": bool(key),
            "key_preview": (key[:10] + "…") if key else ""}


@app.post("/api/settings")
def set_settings(s: SettingsIn):
    cfg = load_config()
    if s.anthropic_api_key is not None:
        cfg["anthropic_api_key"] = s.anthropic_api_key.strip()
    if s.model:
        cfg["model"] = s.model.strip()
    save_config(cfg)
    return {"ok": True, "ai": ai_available()}


# ----- modules

@app.get("/api/modules")
def list_modules():
    conn = db()
    rows = conn.execute(
        """SELECT m.*, COUNT(r.id) AS record_count, MAX(r.ts_effective) AS last_activity
           FROM modules m LEFT JOIN records r ON r.module_id = m.id
           GROUP BY m.id ORDER BY m.name COLLATE NOCASE"""
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["fields"] = json.loads(d.pop("fields_json") or "{}")
        out.append(d)
    return out


@app.post("/api/modules")
def create_module(m: ModuleIn):
    mid = new_id()
    conn = db()
    conn.execute(
        "INSERT INTO modules (id,name,type,fields_json,notes,created_at) VALUES (?,?,?,?,?,?)",
        (mid, m.name.strip(), m.type, json.dumps(m.fields), m.notes, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"id": mid}


@app.get("/api/modules/{mid}")
def get_module(mid: str):
    conn = db()
    r = conn.execute("SELECT * FROM modules WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "Module not found")
    d = dict(r)
    d["fields"] = json.loads(d.pop("fields_json") or "{}")
    return d


@app.patch("/api/modules/{mid}")
def patch_module(mid: str, p: ModulePatch):
    conn = db()
    r = conn.execute("SELECT * FROM modules WHERE id=?", (mid,)).fetchone()
    if not r:
        conn.close()
        raise HTTPException(404, "Module not found")
    name = p.name if p.name is not None else r["name"]
    fields = json.dumps(p.fields) if p.fields is not None else r["fields_json"]
    notes = p.notes if p.notes is not None else r["notes"]
    conn.execute("UPDATE modules SET name=?, fields_json=?, notes=? WHERE id=?",
                 (name, fields, notes, mid))
    conn.commit()
    conn.close()
    if p.name is not None and p.name != r["name"]:
        log_change("module", mid, "name", r["name"], p.name, module_id=mid, label=name)
    if p.fields is not None and json.dumps(p.fields) != r["fields_json"]:
        log_change("module", mid, "fields", r["fields_json"], json.dumps(p.fields), module_id=mid, label=name)
    if p.notes is not None and p.notes != r["notes"]:
        log_change("module", mid, "notes", r["notes"], p.notes, module_id=mid, label=name)
    return {"ok": True}


@app.delete("/api/modules/{mid}")
def delete_module(mid: str):
    conn = db()
    m = conn.execute("SELECT name FROM modules WHERE id=?", (mid,)).fetchone()
    nrec = conn.execute("SELECT COUNT(*) c FROM records WHERE module_id=?", (mid,)).fetchone()["c"]
    files = [r["file_name"] for r in conn.execute(
        "SELECT file_name FROM records WHERE module_id=? AND file_name IS NOT NULL", (mid,))]
    conn.close()
    if m:
        log_change("module", mid, "deleted", m["name"], "",
                   note=f"Module deleted along with its {nrec} record(s)",
                   module_id=mid, label=m["name"])
    conn = db()
    conn.execute("DELETE FROM modules WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    for f in files:
        try:
            (FILES / f).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}


# ----- records

@app.get("/api/modules/{mid}/records")
def module_records(mid: str):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM records WHERE module_id=? ORDER BY COALESCE(ts_effective, created_at) DESC",
        (mid,),
    ).fetchall()
    conn.close()
    return attach_amendments([row_to_record(r) for r in rows])


@app.post("/api/upload")
def upload(  # sync on purpose: runs in the threadpool so long AI calls never block other requests
    module_id: str = Form(...),
    file: UploadFile = File(...),
    user_context: str = Form(""),
    manual_timestamp: str = Form(""),
    title: str = Form(""),
    include_date: str = Form("1"),
):
    conn = db()
    if not conn.execute("SELECT id FROM modules WHERE id=?", (module_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Module not found")
    conn.close()

    rid = new_id()
    orig = file.filename or "upload"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", orig)[-80:]
    stored = f"{rid}_{safe}"
    dest = FILES / stored
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    mime = file.content_type or mimetypes.guess_type(orig)[0] or "application/octet-stream"
    kind = kind_for_mime(mime)
    created = now_iso()
    manual = manual_timestamp.strip() or None

    # initial timestamp: opted-out > manual > EXIF > upload time
    ts, src, conf, score, reason = created, "upload", "guess", 1, "Defaulted to upload time."
    if include_date != "1":
        ts, src, conf, score, reason = None, "none", "", 0, "Dating opted out at upload."
    elif manual:
        ts, src, conf, score, reason = manual, "manual", "exact", 10, "Set manually at upload."
    else:
        ex = exif_datetime(dest) if kind == "image" else None
        if ex:
            ts, src, conf, score = ex, "metadata", "guess", 1
            reason = "From image EXIF capture time — no content evidence yet."

    conn = db()
    conn.execute(
        """INSERT INTO records (id,module_id,kind,title,body,user_context,file_name,
           original_name,mime,ts_effective,ts_source,ts_confidence,ts_score,ts_reasoning,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rid, module_id, kind, title, "", user_context, stored, orig, mime,
         ts, src, conf, score, reason, created),
    )
    conn.commit()
    conn.close()
    log_change("record", rid, "created", "", orig, note=f"Uploaded ({mime})",
               module_id=module_id, label=title or orig)

    ai_error, amended = None, 0
    if ai_available() and is_analyzable(kind, mime):
        try:
            rec = get_record(rid)
            ai_result = analyze_record(rec, dest)
            apply_analysis(rid, ai_result, manual)
            try:
                amended = run_amendment_pass(rid)
            except Exception:
                pass
        except Exception as e:
            ai_error = str(e)
            persist_ai_error(rid, ai_error)

    out = get_record(rid)
    out["ai_error"] = ai_error
    out["amended"] = amended
    return out


@app.post("/api/notes")
def create_note(n: NoteIn):
    conn = db()
    if not conn.execute("SELECT id FROM modules WHERE id=?", (n.module_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "Module not found")
    rid = new_id()
    created = now_iso()
    manual = (n.manual_timestamp or "").strip() or None
    if not n.include_date:
        ts, src, conf, score, reason = None, "none", "", 0, "Dating opted out."
    elif manual:
        ts, src, conf, score, reason = manual, "manual", "exact", 10, "Set manually."
    else:
        ts, src, conf, score, reason = created, "upload", "guess", 1, "Defaulted to creation time."
    link_meta = json.dumps(fetch_link_meta(n.body.strip())) if n.kind == "link" else ""
    conn.execute(
        """INSERT INTO records (id,module_id,kind,title,body,user_context,
           ts_effective,ts_source,ts_confidence,ts_score,ts_reasoning,link_meta,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rid, n.module_id, n.kind, n.title, n.body, n.user_context,
         ts, src, conf, score, reason, link_meta, created),
    )
    conn.commit()
    conn.close()
    log_change("record", rid, "created", "", n.title or n.body[:80], note=f"Added {n.kind}",
               module_id=n.module_id, label=n.title or n.body[:60])

    amended = 0
    if ai_available():
        try:
            rec = get_record(rid)
            result = analyze_record(rec, None)
            apply_analysis(rid, result, manual)
            try:
                amended = run_amendment_pass(rid)
            except Exception:
                pass
        except Exception:
            pass
    out = get_record(rid)
    out["amended"] = amended
    return out


@app.get("/api/records/{rid}")
def get_record(rid: str):
    conn = db()
    r = conn.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "Record not found")
    return attach_amendments([row_to_record(r)])[0]


@app.patch("/api/records/{rid}")
def patch_record(rid: str, p: RecordPatch):
    rec = get_record(rid)
    conn = db()
    sets, vals = [], []

    def set_col(col, val):
        sets.append(f"{col}=?")
        vals.append(val)

    if p.title is not None:
        set_col("title", p.title)
    if p.body is not None:
        set_col("body", p.body)
    if p.user_context is not None:
        set_col("user_context", p.user_context)
    if p.tags is not None:
        set_col("tags_json", json.dumps(p.tags))
    if p.manual_timestamp:
        set_col("ts_effective", p.manual_timestamp)
        set_col("ts_source", "manual")
        set_col("ts_confidence", "exact")
        set_col("ts_score", 10)
        set_col("ts_reasoning", "Set manually.")
    elif p.clear_manual and rec["ts_source"] == "manual":
        ai = rec.get("ai") or {}
        if ai.get("timestamp"):
            try:
                sc = max(1, min(10, int(ai.get("timestamp_score") or 7)))
            except Exception:
                sc = 7
            set_col("ts_effective", ai["timestamp"])
            set_col("ts_source", ai.get("timestamp_source", "content"))
            set_col("ts_confidence", "exact" if sc >= 9 else "approximate" if sc >= 6 else "guess")
            set_col("ts_score", sc)
            set_col("ts_reasoning", ai.get("timestamp_reasoning", ""))
        else:
            set_col("ts_effective", rec["created_at"])
            set_col("ts_source", "upload")
            set_col("ts_confidence", "guess")
            set_col("ts_score", 1)
            set_col("ts_reasoning", "Reverted to upload time.")
    if sets:
        vals.append(rid)
        conn.execute(f"UPDATE records SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    # audit trail for user edits
    mid, lbl = rec["module_id"], record_label(rec)
    if p.title is not None and p.title != rec["title"]:
        log_change("record", rid, "title", rec["title"], p.title, module_id=mid, label=lbl)
    if p.body is not None and p.body != rec["body"]:
        log_change("record", rid, "body", rec["body"], p.body, module_id=mid, label=lbl)
    if p.user_context is not None and p.user_context != rec["user_context"]:
        log_change("record", rid, "context", rec["user_context"], p.user_context, module_id=mid, label=lbl)
    if p.tags is not None and p.tags != rec["tags"]:
        log_change("record", rid, "tags", json.dumps(rec["tags"]), json.dumps(p.tags), module_id=mid, label=lbl)
    if p.manual_timestamp:
        log_change("record", rid, "timestamp",
                   f'{rec["ts_effective"]} ({rec["ts_source"]})',
                   f"{p.manual_timestamp} (manual)", module_id=mid, label=lbl)
    elif p.clear_manual and rec["ts_source"] == "manual":
        log_change("record", rid, "timestamp",
                   f'{rec["ts_effective"]} (manual)', "reverted to AI/metadata date",
                   module_id=mid, label=lbl)
    return get_record(rid)


@app.post("/api/records/{rid}/reanalyze")
def reanalyze(rid: str):
    if not ai_available():
        raise HTTPException(400, "No API key configured")
    rec = get_record(rid)
    path = FILES / rec["file_name"] if rec.get("file_name") else None
    try:
        result = analyze_record(rec, path)
        apply_analysis(rid, result, None if rec["ts_source"] != "manual" else "keep")
    except Exception as e:
        persist_ai_error(rid, str(e))
        raise HTTPException(502, f"AI analysis failed: {e}")
    return get_record(rid)


@app.delete("/api/records/{rid}")
def delete_record(rid: str):
    rec = get_record(rid)
    log_change("record", rid, "deleted",
               json.dumps({k: rec.get(k) for k in
                           ("title", "description", "body", "original_name", "ts_effective")}),
               "", note="Record deleted (snapshot preserved here)",
               module_id=rec["module_id"], label=record_label(rec))
    conn = db()
    conn.execute("DELETE FROM records WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    if rec.get("file_name"):
        try:
            (FILES / rec["file_name"]).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}


class FeedbackIn(BaseModel):
    verdict: str  # up|neutral|down


@app.post("/api/amendments/{aid}/feedback")
def amendment_feedback(aid: str, f: FeedbackIn):
    if f.verdict not in ("up", "neutral", "down"):
        raise HTTPException(400, "verdict must be up, neutral, or down")
    conn = db()
    a = conn.execute("SELECT * FROM amendments WHERE id=?", (aid,)).fetchone()
    if not a:
        conn.close()
        raise HTTPException(404, "Amendment not found")
    if f.verdict in ("down", "neutral"):
        # both revert the change; only 'down' is remembered as a mistake in future prompts
        conn.execute("UPDATE records SET description=? WHERE id=?",
                     (a["old_description"], a["target_record_id"]))
        conn.execute("UPDATE amendments SET verdict=?, status='reversed' WHERE id=?",
                     (f.verdict, aid))
    else:
        conn.execute("UPDATE amendments SET verdict='up' WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    if f.verdict in ("down", "neutral"):
        tmid, tlbl = "", ""
        try:
            trec = get_record(a["target_record_id"])
            tmid, tlbl = trec["module_id"], record_label(trec)
        except Exception:
            pass
        log_change("record", a["target_record_id"], "description",
                   a["new_description"], a["old_description"],
                   note="You rejected an AI amendment — change reversed" if f.verdict == "down"
                   else "You reverted an AI amendment (neutral — not held against the AI)",
                   module_id=tmid, label=tlbl)
    return {"ok": True, "reversed": f.verdict in ("down", "neutral")}


@app.get("/api/audit")
def audit(module_id: Optional[str] = None, limit: int = 300):
    conn = db()
    sql = """SELECT c.*, r.title AS cur_title, r.original_name AS cur_file,
                    m.name AS module_name
             FROM change_log c
             LEFT JOIN records r ON c.entity_type='record' AND r.id = c.entity_id
             LEFT JOIN modules m ON m.id = c.module_id"""
    args = []
    if module_id:
        sql += " WHERE c.module_id=?"
        args.append(module_id)
    sql += " ORDER BY c.created_at DESC LIMIT ?"
    args.append(min(int(limit), 1000))
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/records/{rid}/history")
def record_history(rid: str):
    get_record(rid)  # 404 if missing
    conn = db()
    rows = conn.execute(
        "SELECT * FROM change_log WHERE entity_type='record' AND entity_id=? ORDER BY created_at DESC",
        (rid,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/files/{rid}")
def serve_file(rid: str):
    rec = get_record(rid)
    if not rec.get("file_name"):
        raise HTTPException(404, "No file for this record")
    path = FILES / rec["file_name"]
    if not path.exists():
        raise HTTPException(404, "File missing on disk")
    return FileResponse(path, media_type=rec.get("mime") or "application/octet-stream",
                        filename=rec.get("original_name") or rec["file_name"])


# ----- search / ask / timeline

@app.get("/api/search")
def search(q: str, module_id: Optional[str] = None):
    return {"results": keyword_search(q, module_id)}


@app.post("/api/ask")
def ask(a: AskIn):
    if not ai_available():
        # graceful fallback: keyword search only
        results = keyword_search(a.question, a.module_id)
        return {"answer": "(AI is off — showing keyword matches. Add an API key in Settings for smart search.)",
                "direct": results, "related": [], "ai": False}
    try:
        out = ask_ai(a.question, a.module_id)
        out["ai"] = True
        return out
    except Exception as e:
        results = keyword_search(a.question, a.module_id)
        return {"answer": f"(AI search failed: {e} — showing keyword matches instead.)",
                "direct": results, "related": [], "ai": False}


@app.get("/api/timeline")
def timeline(module_id: Optional[str] = None):
    conn = db()
    sql = """SELECT r.*, m.name AS module_name, m.type AS module_type
             FROM records r JOIN modules m ON m.id = r.module_id"""
    args = []
    if module_id:
        sql += " WHERE r.module_id=?"
        args.append(module_id)
    sql += " ORDER BY COALESCE(r.ts_effective, r.created_at) ASC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return attach_amendments([row_to_record(r) for r in rows])


# ----- static frontend

app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")


if __name__ == "__main__":
    import threading
    import webbrowser

    import uvicorn

    if not os.environ.get("RECEIPTS_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:8765")).start()
    print("\n  Receipts is running →  http://localhost:8765\n")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
