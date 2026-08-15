"""Builders for historical Receipts database shapes.

These recreate what a user's receipts.db actually looked like at each past
schema version, so the migration tests run against the real thing rather than
against a database the current code just created. Add a new builder here
whenever SCHEMA_VERSION is bumped.
"""

import sqlite3
from pathlib import Path

# --- v3: before change_log gained module_id/entity_label (v4), before
# --- records gained ts_score (v5) and link_meta (v6), before modules gained
# --- tags_json (v7) and before the standalone tag registry (v8).
V3_SCHEMA = """
CREATE TABLE modules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'generic',
    fields_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE records (
    id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    user_context TEXT NOT NULL DEFAULT '',
    file_name TEXT,
    original_name TEXT,
    mime TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    ts_effective TEXT,
    ts_source TEXT NOT NULL DEFAULT 'upload',
    ts_confidence TEXT NOT NULL DEFAULT '',
    ts_reasoning TEXT NOT NULL DEFAULT '',
    ai_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE change_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT 'you',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE amendments (
    id TEXT PRIMARY KEY,
    target_record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    source_record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    added_text TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    old_description TEXT NOT NULL DEFAULT '',
    new_description TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
"""

# --- v7: everything except the standalone tag registry.
V7_SCHEMA = V3_SCHEMA.replace(
    "    notes TEXT NOT NULL DEFAULT '',\n    created_at TEXT NOT NULL\n);",
    "    notes TEXT NOT NULL DEFAULT '',\n"
    "    tags_json TEXT NOT NULL DEFAULT '[]',\n"
    "    created_at TEXT NOT NULL\n);",
).replace(
    "    ts_confidence TEXT NOT NULL DEFAULT '',\n    ts_reasoning",
    "    ts_confidence TEXT NOT NULL DEFAULT '',\n"
    "    ts_score INTEGER NOT NULL DEFAULT 0,\n"
    "    ts_reasoning",
).replace(
    "    ai_json TEXT NOT NULL DEFAULT '{}',",
    "    link_meta TEXT NOT NULL DEFAULT '',\n    ai_json TEXT NOT NULL DEFAULT '{}',",
).replace(
    "    note TEXT NOT NULL DEFAULT '',\n    created_at TEXT NOT NULL\n);",
    "    note TEXT NOT NULL DEFAULT '',\n"
    "    module_id TEXT NOT NULL DEFAULT '',\n"
    "    entity_label TEXT NOT NULL DEFAULT '',\n"
    "    created_at TEXT NOT NULL\n);",
)

NOW = "2026-01-15T10:00:00+00:00"

# Deliberately varied ts_source/ts_confidence so the v5 backfill mapping is
# exercised across every branch of its CASE expression.
RECORDS = [
    # (id, kind, title, ts_source, ts_confidence, expected ts_score after v5)
    ("rec_manual", "image", "Brewskys with Laura", "manual", "", 10),
    ("rec_exact", "image", "Concert tickets", "content", "exact", 10),
    ("rec_approx", "note", "Coffee shop chat", "content", "approximate", 7),
    ("rec_guess", "link", "Some article", "upload", "", 1),
    ("rec_meta", "video", "Birthday clip", "metadata", "", 1),
]


def build(path: Path, version: int) -> None:
    """Create a populated legacy database at `path` with PRAGMA user_version."""
    schema = {3: V3_SCHEMA, 7: V7_SCHEMA}[version]
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(schema)

    if version >= 7:
        conn.execute(
            "INSERT INTO modules (id,name,type,fields_json,notes,tags_json,created_at)"
            " VALUES ('mod_laura','Laura','person','{}','',?,?)",
            ('["friend","austin"]', NOW),
        )
    else:
        conn.execute(
            "INSERT INTO modules (id,name,type,fields_json,notes,created_at)"
            " VALUES ('mod_laura','Laura','person','{}','',?)",
            (NOW,),
        )

    for rid, kind, title, ts_source, ts_conf, _ in RECORDS:
        cols = "id,module_id,kind,title,body,description,user_context,tags_json," \
               "ts_effective,ts_source,ts_confidence,ts_reasoning,ai_json,created_at"
        vals = [rid, "mod_laura", kind, title, "body text", "a description",
                "context", '["memory"]', NOW, ts_source, ts_conf, "", "{}", NOW]
        conn.execute(
            f"INSERT INTO records ({cols}) VALUES ({','.join('?' * len(vals))})", vals
        )

    # One change_log row per entity type, so the v4 backfill is exercised both ways.
    base = "id,entity_type,entity_id,field,old_value,new_value,actor,note,created_at"
    conn.execute(
        f"INSERT INTO change_log ({base}) VALUES (?,?,?,?,?,?,?,?,?)",
        ("cl_1", "record", "rec_manual", "created", "", "", "you", "", NOW),
    )
    conn.execute(
        f"INSERT INTO change_log ({base}) VALUES (?,?,?,?,?,?,?,?,?)",
        ("cl_2", "module", "mod_laura", "created", "", "", "you", "", NOW),
    )

    conn.execute(
        "INSERT INTO amendments (id,target_record_id,source_record_id,added_text,"
        "reason,old_description,new_description,verdict,status,created_at)"
        " VALUES ('am_1','rec_manual','rec_exact','more detail','because','old','new','','active',?)",
        (NOW,),
    )

    conn.execute(f"PRAGMA user_version={version}")
    conn.commit()
    conn.close()
