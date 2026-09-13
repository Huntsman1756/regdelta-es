from __future__ import annotations

import sqlite3
from pathlib import Path

SOURCE_IDS = (
    "boe_sumario", "bde_consultas",
    "boe_diario", "boe_doc", "boe_pdf", "boe_imagen",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_blobs (
  sha256      TEXT PRIMARY KEY CHECK (length(sha256) = 64),
  size_bytes  INTEGER NOT NULL CHECK (size_bytes >= 0),
  stored_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  snapshot_id       TEXT PRIMARY KEY CHECK (length(snapshot_id) = 64),
  source_id         TEXT NOT NULL CHECK (source_id IN ('boe_sumario', 'bde_consultas', 'boe_diario', 'boe_doc', 'boe_pdf', 'boe_imagen')),
  source_url        TEXT NOT NULL,
  blob_sha256       TEXT NOT NULL REFERENCES source_blobs(sha256),
  source_date       TEXT,
  source_updated_at TEXT,
  parse_status      TEXT NOT NULL CHECK (parse_status IN ('COMPLETE', 'INVALID_STRUCTURE')),
  parse_error       TEXT,
  parser_name       TEXT NOT NULL,
  parser_version    TEXT NOT NULL,
  has_anomalies     INTEGER NOT NULL DEFAULT 0 CHECK (has_anomalies IN (0, 1)),
  first_checked_at  TEXT NOT NULL,
  UNIQUE (source_id, source_url, blob_sha256)
);

CREATE TABLE IF NOT EXISTS source_checks (
  check_id      TEXT PRIMARY KEY CHECK (length(check_id) = 64),
  source_id     TEXT NOT NULL CHECK (source_id IN ('boe_sumario', 'bde_consultas', 'boe_diario', 'boe_doc', 'boe_pdf', 'boe_imagen')),
  source_url    TEXT NOT NULL,
  checked_at    TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('OK', 'PARSE_INVALID', 'FETCH_ERROR')),
  http_status   INTEGER,
  media_type    TEXT,
  snapshot_id   TEXT REFERENCES source_snapshots(snapshot_id),
  error_class   TEXT,
  error_message TEXT,
  CHECK (
    (status IN ('OK', 'PARSE_INVALID') AND snapshot_id IS NOT NULL)
    OR (status = 'FETCH_ERROR' AND snapshot_id IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS boe_items (
  item_uid                TEXT PRIMARY KEY,
  first_seen_snapshot_id  TEXT NOT NULL REFERENCES source_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS boe_item_placements (
  snapshot_id         TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
  item_uid            TEXT NOT NULL REFERENCES boe_items(item_uid),
  fecha_sumario       TEXT NOT NULL,
  seccion_codigo      TEXT NOT NULL,
  seccion_nombre      TEXT NOT NULL,
  departamento_codigo TEXT NOT NULL,
  departamento_nombre TEXT NOT NULL,
  epigrafe            TEXT,
  titulo              TEXT NOT NULL,
  control             TEXT,
  url_xml             TEXT,
  url_html            TEXT,
  url_pdf             TEXT,
  PRIMARY KEY (snapshot_id, item_uid)
);

CREATE TABLE IF NOT EXISTS bde_consultations (
  consultation_uid        TEXT PRIMARY KEY CHECK (length(consultation_uid) = 64),
  title_normalized        TEXT NOT NULL,
  published_on            TEXT NOT NULL,
  first_seen_snapshot_id  TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
  UNIQUE (title_normalized, published_on)
);

CREATE TABLE IF NOT EXISTS bde_snapshot_memberships (
  snapshot_id         TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
  consultation_uid    TEXT NOT NULL REFERENCES bde_consultations(consultation_uid),
  position_in_page    INTEGER NOT NULL,
  title_raw           TEXT NOT NULL,
  consultation_end_on TEXT,
  anuncio_pdf_urls    TEXT NOT NULL,
  project_pdf_urls    TEXT NOT NULL,
  other_document_urls TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, consultation_uid)
);

CREATE TABLE IF NOT EXISTS anomalies (
  anomaly_id  TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  snapshot_id TEXT REFERENCES source_snapshots(snapshot_id),
  detail      TEXT NOT NULL,
  detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checks_source_time ON source_checks(source_id, checked_at);
CREATE INDEX IF NOT EXISTS idx_memberships_entity ON bde_snapshot_memberships(consultation_uid);
CREATE INDEX IF NOT EXISTS idx_placements_item ON boe_item_placements(item_uid);

CREATE TABLE IF NOT EXISTS instruments (
  instrument_id        TEXT PRIMARY KEY CHECK (length(instrument_id) = 64),
  boe_id               TEXT NOT NULL UNIQUE,
  titulo               TEXT NOT NULL,
  rango                TEXT,
  fecha_disposicion    TEXT,
  fecha_publicacion    TEXT,
  fecha_vigencia       TEXT,
  estado_consolidacion TEXT,
  origin               TEXT NOT NULL CHECK (origin IN ('PARSED', 'REFERENCED')),
  snapshot_id          TEXT REFERENCES source_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS subjects (
  subject_id    TEXT PRIMARY KEY CHECK (length(subject_id) = 64),
  instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
  locator_key   TEXT NOT NULL,
  label         TEXT NOT NULL,
  subject_kind  TEXT NOT NULL CHECK (subject_kind IN
                ('NORMA', 'ESTADO', 'ANEJO', 'PUNTO', 'APARTADO', 'INDICE',
                 'DISPOSICION', 'NOTA', 'INSTRUMENT')),
  UNIQUE (instrument_id, locator_key)
);

CREATE TABLE IF NOT EXISTS representations (
  representation_id   TEXT PRIMARY KEY CHECK (length(representation_id) = 64),
  subject_id          TEXT NOT NULL REFERENCES subjects(subject_id),
  representation_kind TEXT NOT NULL CHECK (representation_kind IN
                      ('TEXT', 'TABLE', 'IMAGE', 'PDF_PAGE')),
  content_sha256      TEXT NOT NULL CHECK (length(content_sha256) = 64),
  text_content        TEXT,
  artifact_locator    TEXT NOT NULL,
  source_snapshot_id  TEXT NOT NULL REFERENCES source_snapshots(snapshot_id),
  binding             TEXT NOT NULL CHECK (binding IN
                      ('DECLARED', 'ANCHORED_DERIVED', 'UNANCHORED_DERIVED')),
  binding_evidence    TEXT NOT NULL,
  parser_name         TEXT NOT NULL,
  parser_version      TEXT NOT NULL,
  CHECK (
    (representation_kind IN ('TEXT', 'TABLE') AND text_content IS NOT NULL)
    OR (representation_kind IN ('IMAGE', 'PDF_PAGE') AND text_content IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS instrument_relations (
  instrument_relation_id TEXT PRIMARY KEY CHECK (length(instrument_relation_id) = 64),
  declaring_instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
  direction               TEXT NOT NULL CHECK (direction IN ('ANTERIOR', 'POSTERIOR')),
  other_boe_id            TEXT NOT NULL,
  other_instrument_id     TEXT REFERENCES instruments(instrument_id),
  palabra                 TEXT NOT NULL,
  palabra_codigo          TEXT,
  descripcion             TEXT,
  source_snapshot_id      TEXT NOT NULL REFERENCES source_snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS modification_relations (
  relation_id            TEXT PRIMARY KEY CHECK (length(relation_id) = 64),
  kind                   TEXT NOT NULL CHECK (kind IN ('MODIFICATION', 'CORRECTION')),
  operation_kind         TEXT NOT NULL CHECK (operation_kind IN
                         ('SUBSTITUTE', 'MODIFY', 'ADD', 'DELETE', 'CORRECT')),
  target_subject_id      TEXT NOT NULL REFERENCES subjects(subject_id),
  modifier_instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
  locator_raw            TEXT NOT NULL,
  relation_raw           TEXT,
  before_representation_id TEXT REFERENCES representations(representation_id),
  after_representation_id  TEXT REFERENCES representations(representation_id),
  publication_date       TEXT NOT NULL,
  effective_date         TEXT,
  declared_literals      TEXT,
  diff_levels            TEXT NOT NULL,
  resolution             TEXT NOT NULL CHECK (resolution IN
                         ('RESOLVED', 'PARTIAL', 'UNRESOLVED')),
  resolution_notes       TEXT,
  source_snapshot_ids    TEXT NOT NULL,
  parser_name            TEXT NOT NULL,
  parser_version         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repr_subject ON representations(subject_id);
CREATE INDEX IF NOT EXISTS idx_modrel_subject ON modification_relations(target_subject_id);
CREATE INDEX IF NOT EXISTS idx_modrel_modifier ON modification_relations(modifier_instrument_id);
CREATE INDEX IF NOT EXISTS idx_irel_other ON instrument_relations(other_boe_id);
"""


def _ensure_parser_provenance_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_snapshots)")}
    if "parser_name" not in columns:
        conn.execute("ALTER TABLE source_snapshots ADD COLUMN parser_name TEXT")
    if "parser_version" not in columns:
        conn.execute("ALTER TABLE source_snapshots ADD COLUMN parser_version TEXT")
    conn.execute(
        "UPDATE source_snapshots SET parser_name = CASE source_id"
        " WHEN 'boe_sumario' THEN 'boe_sumario' ELSE 'bde_consultas' END"
        " WHERE parser_name IS NULL"
    )
    conn.execute(
        "UPDATE source_snapshots SET parser_version = 'v1' WHERE parser_version IS NULL"
    )


def _rebuild_table(conn: sqlite3.Connection, table: str, cols: str,
                   create_sql: str,
                   post_sql: tuple[str, ...] = ()) -> None:
    """Rebuild ``table`` in place preserving every row and every inbound
    foreign key.

    SQLite cannot alter a CHECK constraint; the only in-place evolution is
    create-new + copy + drop + rename. RENAME TO rewrites REFERENCES
    clauses pointing at the renamed table, so the *old* table is dropped
    under its own name instead of being renamed away (renaming it would
    permanently retarget child FKs at ``<table>_old``). Columns are copied
    by name — column order differs on databases that grew columns through
    ALTER TABLE, so ``SELECT *`` would corrupt rows. ``executescript``
    must NOT be used inside the transaction: it issues an implicit COMMIT
    first, breaking the surrounding BEGIN/ROLLBACK handling.
    """
    new_table = f"{table}__new"
    new_sql = create_sql.replace(
        f"CREATE TABLE {table} ", f"CREATE TABLE {new_table} ", 1)
    assert new_sql != create_sql
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(new_sql)
        conn.execute(
            f"INSERT INTO {new_table} ({cols}) SELECT {cols} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {new_table} RENAME TO {table}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise sqlite3.IntegrityError(
            f"foreign_key_check failed after rebuilding {table}:"
            f" {violations[:5]}")
    for stmt in post_sql:
        conn.execute(stmt)


def _ensure_source_ids(conn: sqlite3.Connection) -> None:
    """Rebuild source_snapshots if its CHECK predates the G0-C source kinds."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_snapshots'"
    ).fetchone()
    if row is None or "boe_diario" in (row[0] or ""):
        return
    _rebuild_table(conn, "source_snapshots",
                   "snapshot_id, source_id, source_url, blob_sha256,"
                   " source_date, source_updated_at, parse_status,"
                   " parse_error, parser_name, parser_version,"
                   " has_anomalies, first_checked_at",
                   """
        CREATE TABLE source_snapshots (
          snapshot_id       TEXT PRIMARY KEY CHECK (length(snapshot_id) = 64),
          source_id         TEXT NOT NULL CHECK (source_id IN ('boe_sumario', 'bde_consultas', 'boe_diario', 'boe_doc', 'boe_pdf', 'boe_imagen')),
          source_url        TEXT NOT NULL,
          blob_sha256       TEXT NOT NULL REFERENCES source_blobs(sha256),
          source_date       TEXT,
          source_updated_at TEXT,
          parse_status      TEXT NOT NULL CHECK (parse_status IN ('COMPLETE', 'INVALID_STRUCTURE')),
          parse_error       TEXT,
          parser_name       TEXT NOT NULL,
          parser_version    TEXT NOT NULL,
          has_anomalies     INTEGER NOT NULL DEFAULT 0 CHECK (has_anomalies IN (0, 1)),
          first_checked_at  TEXT NOT NULL,
          UNIQUE (source_id, source_url, blob_sha256)
        )""")


def _ensure_check_source_ids(conn: sqlite3.Connection) -> None:
    """Rebuild source_checks if its CHECK predates the G0-C source kinds.

    G0-C.2R: every runtime source produces checks, not only the two
    watcher sources. Rows are preserved; only the constraint widens.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='source_checks'"
    ).fetchone()
    if row is None or "boe_diario" in (row[0] or ""):
        return
    _rebuild_table(conn, "source_checks",
                   "check_id, source_id, source_url, checked_at, status,"
                   " http_status, media_type, snapshot_id, error_class,"
                   " error_message",
                   """
        CREATE TABLE source_checks (
          check_id      TEXT PRIMARY KEY CHECK (length(check_id) = 64),
          source_id     TEXT NOT NULL CHECK (source_id IN ('boe_sumario', 'bde_consultas', 'boe_diario', 'boe_doc', 'boe_pdf', 'boe_imagen')),
          source_url    TEXT NOT NULL,
          checked_at    TEXT NOT NULL,
          status        TEXT NOT NULL CHECK (status IN ('OK', 'PARSE_INVALID', 'FETCH_ERROR')),
          http_status   INTEGER,
          media_type    TEXT,
          snapshot_id   TEXT REFERENCES source_snapshots(snapshot_id),
          error_class   TEXT,
          error_message TEXT,
          CHECK (
            (status IN ('OK', 'PARSE_INVALID') AND snapshot_id IS NOT NULL)
            OR (status = 'FETCH_ERROR' AND snapshot_id IS NULL)
          )
        )""", post_sql=(
        "CREATE INDEX IF NOT EXISTS idx_checks_source_time"
        " ON source_checks(source_id, checked_at)",
    ))


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.isolation_level = None
    conn.executescript(SCHEMA)
    _ensure_parser_provenance_columns(conn)
    _ensure_source_ids(conn)
    _ensure_check_source_ids(conn)
    return conn
