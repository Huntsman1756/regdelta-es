"""Import captured evidence manifests into the runtime raw store.

The G0-C/G0-C.1 evidence directories keep raw official artifacts with a
``manifest.json`` (entries: path, url, sha256, retrieved_at). Importing them
into a RegDelta database produces the same snapshot identities as a live
fetch would (``snap|source_id|url|blob_sha256``), so tests and offline
reconstruction share the production evidence model.
"""

from __future__ import annotations

import json
from pathlib import Path

from .profile import active_profile
from .rawstore import store_blob
from .sources import boe_diario, boe_doc, boe_pdf
from .util import sha256_hex, sha256_hex_text

_PARSERS = {
    "boe_diario": (boe_diario.PARSER_NAME, boe_diario.PARSER_VERSION),
    "boe_doc": (boe_doc.PARSER_NAME, boe_doc.PARSER_VERSION),
    "boe_pdf": (boe_pdf.PARSER_NAME, boe_pdf.PARSER_VERSION),
    "boe_imagen": None,  # resolved from profile descriptors below
}


def _parsers() -> dict:
    sd = active_profile().source_descriptors
    out = dict(_PARSERS)
    out["boe_imagen"] = sd.imagen_parser
    return out


def _source_id(name: str, path: str) -> str:
    """Capture-layout rules: (name prefix, path suffix) -> source id."""
    sd = active_profile().source_descriptors
    for prefix, suffix, sid in sd.capture_rules:
        if (prefix is not None and name.startswith(prefix)) \
                or (suffix is not None and path.endswith(suffix)):
            return sid
    return sd.capture_default


def import_manifest(
    conn,
    data_dir: Path,
    manifest_path: Path,
    names: list[str] | None = None,
) -> dict[str, str]:
    """Import manifest entries; returns ``{logical_name: snapshot_id}``."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    # manifest entry paths are repo-relative ("evidence/<gate>/raw/...")
    root = Path(manifest_path).resolve().parents[3]
    out: dict[str, str] = {}
    for name, entry in manifest["entries"].items():
        if names is not None and name not in names:
            continue
        data = (root / entry["path"]).read_bytes()
        sha = sha256_hex(data)
        if sha != entry["sha256"]:
            raise ValueError(
                f"evidence integrity failure: {name} sha256 mismatch")
        store_blob(Path(data_dir), data)
        conn.execute(
            "INSERT OR IGNORE INTO source_blobs (sha256, size_bytes, stored_at)"
            " VALUES (?,?,?)",
            (sha, len(data), entry["retrieved_at"]),
        )
        source_id = _source_id(name, entry["path"])
        parser_name, parser_version = _parsers()[source_id]
        snapshot_id = sha256_hex_text(
            f"snap|{source_id}|{entry['url']}|{sha}")
        conn.execute(
            "INSERT OR IGNORE INTO source_snapshots (snapshot_id, source_id,"
            " source_url, blob_sha256, source_date, source_updated_at,"
            " parse_status, parse_error, parser_name, parser_version,"
            " has_anomalies, first_checked_at)"
            " VALUES (?,?,?,?,?,NULL,'COMPLETE',NULL,?,?,0,?)",
            (
                snapshot_id, source_id, entry["url"], sha, None,
                parser_name, parser_version, entry["retrieved_at"],
            ),
        )
        out[name] = snapshot_id
    return out
