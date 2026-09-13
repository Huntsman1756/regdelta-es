from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin
from uuid import uuid4

from . import db as dbm
from . import state
from .config import (
    ACCEPT_HTML,
    ACCEPT_XML,
    BDE_CONSULTAS_URL,
    boe_sumario_url,
)
from .http import FetchResult, http_fetch
from .rawstore import store_blob
from .sources import bde_consultas, boe_sumario
from .util import normalize_title, now_utc_iso, sha256_hex, sha256_hex_text

ANOMALY_DUPLICATE_ITEM = "DUPLICATE_ITEM_IN_SNAPSHOT"
ANOMALY_DUPLICATE_CONSULTATION = "DUPLICATE_CONSULTATION_IN_SNAPSHOT"

EXIT_OK = 0
EXIT_ANOMALY = 2
EXIT_SOURCE_PROBLEM = 3


def _snapshot_id(source_id: str, url: str, blob_sha256: str) -> str:
    return sha256_hex_text(f"snap|{source_id}|{url}|{blob_sha256}")


def consultation_uid(title_normalized: str, published_on: str) -> str:
    return sha256_hex_text(f"bde_consultation|{title_normalized}|{published_on}")


def _check_id(source_id: str, url: str, blob_sha256: str | None, checked_at: str) -> str:
    return sha256_hex_text(
        f"check|{source_id}|{url}|{blob_sha256 or ''}|{checked_at}|{uuid4().hex}"
    )


def _anomaly_id(kind: str, detail: str) -> str:
    return sha256_hex_text(f"anomaly|{kind}|{detail}")


def _fetch_error_check(
    conn, source_id: str, url: str, checked_at: str, fetch_result: FetchResult
) -> dict:
    check_pk = _check_id(source_id, url, None, checked_at)
    conn.execute(
        "INSERT INTO source_checks (check_id, source_id, source_url, checked_at, status,"
        " http_status, media_type, snapshot_id, error_class, error_message)"
        " VALUES (?,?,?,?,'FETCH_ERROR',?,?,NULL,?,?)",
        (
            check_pk,
            source_id,
            url,
            checked_at,
            fetch_result.http_status,
            fetch_result.media_type,
            fetch_result.error_class,
            fetch_result.error_message,
        ),
    )
    return {
        "source_id": source_id,
        "url": url,
        "status": "FETCH_ERROR",
        "http_status": fetch_result.http_status,
        "error_class": fetch_result.error_class,
        "error_message": fetch_result.error_message,
        "blob_sha256": None,
        "snapshot_id": None,
        "snapshot_new": False,
        "parse_status": None,
        "entities_new": 0,
        "anomalies": [],
    }


def _persist_snapshot(
    conn,
    source_id: str,
    url: str,
    blob_sha256: str,
    body: bytes,
    checked_at: str,
    media_type: str | None,
    source_date: str | None,
    parse_status: str,
    parse_error: str | None,
    parser_name: str,
    parser_version: str,
    http_status: int | None,
) -> tuple[str, bool]:
    conn.execute(
        "INSERT OR IGNORE INTO source_blobs (sha256, size_bytes, stored_at) VALUES (?,?,?)",
        (blob_sha256, len(body), checked_at),
    )
    snapshot_pk = _snapshot_id(source_id, url, blob_sha256)
    cursor = conn.execute(
        "INSERT OR IGNORE INTO source_snapshots (snapshot_id, source_id, source_url,"
        " blob_sha256, source_date, source_updated_at, parse_status, parse_error,"
        " parser_name, parser_version, has_anomalies, first_checked_at)"
        " VALUES (?,?,?,?,?,NULL,?,?,?,?,0,?)",
        (
            snapshot_pk,
            source_id,
            url,
            blob_sha256,
            source_date,
            parse_status,
            parse_error,
            parser_name,
            parser_version,
            checked_at,
        ),
    )
    snapshot_new = cursor.rowcount == 1
    status = "OK" if parse_status == "COMPLETE" else "PARSE_INVALID"
    conn.execute(
        "INSERT INTO source_checks (check_id, source_id, source_url, checked_at, status,"
        " http_status, media_type, snapshot_id, error_class, error_message)"
        " VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
        ( _check_id(source_id, url, blob_sha256, checked_at), source_id, url, checked_at,
          status, http_status, media_type, snapshot_pk ),
    )
    return snapshot_pk, snapshot_new


def _insert_anomaly(conn, kind: str, snapshot_id: str, detail: str, detected_at: str) -> str:
    anomaly_pk = _anomaly_id(kind, detail)
    conn.execute(
        "INSERT OR IGNORE INTO anomalies (anomaly_id, kind, snapshot_id, detail, detected_at)"
        " VALUES (?,?,?,?,?)",
        (anomaly_pk, kind, snapshot_id, detail, detected_at),
    )
    return anomaly_pk


def _insert_boe_derived(conn, snapshot_id: str, items: list, detected_at: str) -> tuple[int, list[str]]:
    identifiers = [item.identificador for item in items]
    duplicates = sorted({ident for ident in identifiers if identifiers.count(ident) > 1})
    if duplicates:
        anomaly_ids = []
        for ident in duplicates:
            detail = json.dumps(
                {
                    "identificador": ident,
                    "titulos": [i.titulo for i in items if i.identificador == ident],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            anomaly_ids.append(
                _insert_anomaly(conn, ANOMALY_DUPLICATE_ITEM, snapshot_id, detail, detected_at)
            )
        return 0, anomaly_ids
    entities_new = 0
    for item in items:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO boe_items (item_uid, first_seen_snapshot_id) VALUES (?,?)",
            (item.identificador, snapshot_id),
        )
        entities_new += cursor.rowcount
        conn.execute(
            "INSERT INTO boe_item_placements (snapshot_id, item_uid, fecha_sumario,"
            " seccion_codigo, seccion_nombre, departamento_codigo, departamento_nombre,"
            " epigrafe, titulo, control, url_xml, url_html, url_pdf)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                snapshot_id,
                item.identificador,
                item.fecha_sumario,
                item.seccion_codigo,
                item.seccion_nombre,
                item.departamento_codigo,
                item.departamento_nombre,
                item.epigrafe,
                item.titulo,
                item.control,
                item.url_xml,
                item.url_html,
                item.url_pdf,
            ),
        )
    return entities_new, []


def _insert_consultas_derived(conn, snapshot_id: str, entries: list, base_url: str, detected_at: str) -> tuple[int, list[str]]:
    keys = [(normalize_title(entry.title_raw), entry.published_on) for entry in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        anomaly_ids = []
        for title_normalized, published_on in duplicates:
            detail = json.dumps(
                {
                    "title_normalized": title_normalized,
                    "published_on": published_on,
                    "titulos_raw": [
                        e.title_raw for e in entries
                        if (normalize_title(e.title_raw), e.published_on) == (title_normalized, published_on)
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            anomaly_ids.append(
                _insert_anomaly(
                    conn, ANOMALY_DUPLICATE_CONSULTATION, snapshot_id, detail, detected_at
                )
            )
        return 0, anomaly_ids
    entities_new = 0
    for position, entry in enumerate(entries):
        title_normalized = normalize_title(entry.title_raw)
        consultation_pk = consultation_uid(title_normalized, entry.published_on)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO bde_consultations (consultation_uid, title_normalized,"
            " published_on, first_seen_snapshot_id) VALUES (?,?,?,?)",
            (consultation_pk, title_normalized, entry.published_on, snapshot_id),
        )
        entities_new += cursor.rowcount
        conn.execute(
            "INSERT INTO bde_snapshot_memberships (snapshot_id, consultation_uid,"
            " position_in_page, title_raw, consultation_end_on, anuncio_pdf_urls,"
            " project_pdf_urls, other_document_urls) VALUES (?,?,?,?,?,?,?,?)",
            (
                snapshot_id,
                consultation_pk,
                position,
                entry.title_raw,
                entry.consultation_end_on,
                json.dumps([urljoin(base_url, u) for u in entry.anuncio_pdf_urls], ensure_ascii=False),
                json.dumps([urljoin(base_url, u) for u in entry.project_pdf_urls], ensure_ascii=False),
                json.dumps([urljoin(base_url, u) for u in entry.other_document_urls], ensure_ascii=False),
            ),
        )
    return entities_new, []


def _is_fetch_error(fetch_result: FetchResult) -> bool:
    return (
        fetch_result.body is None
        or fetch_result.error_class is not None
        or (
            fetch_result.http_status is not None
            and fetch_result.http_status != 200
        )
    )


def _prepare_sumario(date_iso: str, data_dir: Path, fetch_fn) -> dict:
    source_id = "boe_sumario"
    url = boe_sumario_url(date_iso)
    checked_at = now_utc_iso()
    fetch_result = fetch_fn(url, ACCEPT_XML)
    prepared = {
        "source_id": source_id,
        "url": url,
        "checked_at": checked_at,
        "fetch": fetch_result,
        "body": fetch_result.body,
        "blob_sha256": None,
        "parse": None,
    }
    if _is_fetch_error(fetch_result):
        return prepared
    prepared["blob_sha256"], _path = store_blob(data_dir, fetch_result.body)
    prepared["parse"] = boe_sumario.parse_sumario(fetch_result.body, date_iso)
    return prepared


def _prepare_consultas(data_dir: Path, fetch_fn) -> dict:
    source_id = "bde_consultas"
    url = BDE_CONSULTAS_URL
    checked_at = now_utc_iso()
    fetch_result = fetch_fn(url, ACCEPT_HTML)
    prepared = {
        "source_id": source_id,
        "url": url,
        "checked_at": checked_at,
        "fetch": fetch_result,
        "body": fetch_result.body,
        "blob_sha256": None,
        "parse": None,
    }
    if _is_fetch_error(fetch_result):
        return prepared
    prepared["blob_sha256"], _path = store_blob(data_dir, fetch_result.body)
    prepared["parse"] = bde_consultas.parse_consultas(
        fetch_result.body, fetch_result.media_type
    )
    return prepared


def _persist_sumario(conn, prepared: dict) -> dict:
    source_id = prepared["source_id"]
    url = prepared["url"]
    checked_at = prepared["checked_at"]
    fetch_result = prepared["fetch"]
    if _is_fetch_error(fetch_result):
        return _fetch_error_check(conn, source_id, url, checked_at, fetch_result)
    result = prepared["parse"]
    snapshot_id, snapshot_new = _persist_snapshot(
        conn,
        source_id,
        url,
        prepared["blob_sha256"],
        prepared["body"],
        checked_at,
        fetch_result.media_type,
        result.source_date,
        result.parse_status,
        result.parse_error,
        boe_sumario.PARSER_NAME,
        boe_sumario.PARSER_VERSION,
        fetch_result.http_status,
    )
    out = {
        "source_id": source_id,
        "url": url,
        "status": "OK" if result.parse_status == boe_sumario.COMPLETE else "PARSE_INVALID",
        "http_status": fetch_result.http_status,
        "media_type": fetch_result.media_type,
        "error_class": None,
        "error_message": None,
        "blob_sha256": prepared["blob_sha256"],
        "snapshot_id": snapshot_id,
        "snapshot_new": snapshot_new,
        "parse_status": result.parse_status,
        "parse_error": result.parse_error,
        "parser_name": boe_sumario.PARSER_NAME,
        "parser_version": boe_sumario.PARSER_VERSION,
        "source_date": result.source_date,
        "entities_new": 0,
        "anomalies": [],
    }
    if snapshot_new and result.parse_status == boe_sumario.COMPLETE:
        entities_new, anomaly_ids = _insert_boe_derived(conn, snapshot_id, result.items, checked_at)
        out["entities_new"] = entities_new
        out["anomalies"] = anomaly_ids
        if anomaly_ids:
            conn.execute(
                "UPDATE source_snapshots SET has_anomalies = 1 WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            out["status"] = "OK_WITH_ANOMALIES"
    return out


def _persist_consultas(conn, prepared: dict) -> dict:
    source_id = prepared["source_id"]
    url = prepared["url"]
    checked_at = prepared["checked_at"]
    fetch_result = prepared["fetch"]
    if _is_fetch_error(fetch_result):
        return _fetch_error_check(conn, source_id, url, checked_at, fetch_result)
    result = prepared["parse"]
    snapshot_id, snapshot_new = _persist_snapshot(
        conn,
        source_id,
        url,
        prepared["blob_sha256"],
        prepared["body"],
        checked_at,
        fetch_result.media_type,
        None,
        result.parse_status,
        result.parse_error,
        bde_consultas.PARSER_NAME,
        bde_consultas.PARSER_VERSION,
        fetch_result.http_status,
    )
    out = {
        "source_id": source_id,
        "url": url,
        "status": "OK" if result.parse_status == bde_consultas.COMPLETE else "PARSE_INVALID",
        "http_status": fetch_result.http_status,
        "media_type": fetch_result.media_type,
        "error_class": None,
        "error_message": None,
        "blob_sha256": prepared["blob_sha256"],
        "snapshot_id": snapshot_id,
        "snapshot_new": snapshot_new,
        "parse_status": result.parse_status,
        "parse_error": result.parse_error,
        "parser_name": bde_consultas.PARSER_NAME,
        "parser_version": bde_consultas.PARSER_VERSION,
        "source_date": None,
        "entities_new": 0,
        "anomalies": [],
    }
    if snapshot_new and result.parse_status == bde_consultas.COMPLETE:
        entities_new, anomaly_ids = _insert_consultas_derived(
            conn, snapshot_id, result.entries, url, checked_at
        )
        out["entities_new"] = entities_new
        out["anomalies"] = anomaly_ids
        if anomaly_ids:
            conn.execute(
                "UPDATE source_snapshots SET has_anomalies = 1 WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            out["status"] = "OK_WITH_ANOMALIES"
    return out


def run(date_iso: str, data_dir: Path, fetch_fn=http_fetch) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    conn = dbm.connect(data_dir / "regdelta.sqlite")
    try:
        prepared = [
            _prepare_sumario(date_iso, data_dir, fetch_fn),
            _prepare_consultas(data_dir, fetch_fn),
        ]
        conn.execute("BEGIN IMMEDIATE")
        try:
            results = [
                _persist_sumario(conn, prepared[0]),
                _persist_consultas(conn, prepared[1]),
            ]
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    anomalies = [aid for r in results for aid in r["anomalies"]]
    problems = [r for r in results if r["status"] in ("FETCH_ERROR", "PARSE_INVALID")]
    if anomalies:
        exit_code = EXIT_ANOMALY
    elif problems:
        exit_code = EXIT_SOURCE_PROBLEM
    else:
        exit_code = EXIT_OK
    return {"date": date_iso, "sources": results, "exit_code": exit_code}


def latest_state_snapshot(conn, source_id: str) -> str | None:
    return state.latest_complete_snapshot_id(conn, source_id)
