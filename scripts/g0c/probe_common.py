"""G0-C discovery: shared fetch / content-addressed evidence capture helpers.

This module is deliberately isolated from the regdelta runtime. It only uses the
Python standard library so it can be executed directly (``python scripts/g0c/...``)
inside the checked-out repository without importing the product package.

Evidence model (mirrors G0-A/B philosophy, but scoped to evidence/g0c):

* every HTTP fetch is recorded in ``evidence/g0c/raw/manifest.json`` with the
  exact request Accept header, the real retrieval timestamp, HTTP status,
  content type, byte size and SHA-256;
* raw bytes are stored under ``evidence/g0c/raw/`` keyed by a stable logical
  name so a human can diff channels;
* nothing is inferred here: this module only OBSERVES bytes.

No LLM, no parsing heuristics, no network side effects beyond GET.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "g0c"
RAW_DIR = EVIDENCE_DIR / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 RegDelta-G0C/0.1"
)
TIMEOUT_SECONDS = 120

ACCEPT_XML = "application/xml"
ACCEPT_HTML = "text/html"
ACCEPT_PDF = "application/pdf"
ACCEPT_ANY = "*/*"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FetchResult:
    url: str
    accept: str
    http_status: int | None
    content_type: str | None
    body: bytes | None
    error_class: str | None
    error_message: str | None


def fetch(url: str, accept: str = ACCEPT_ANY) -> FetchResult:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "es-ES,es;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return FetchResult(
                url=url,
                accept=accept,
                http_status=response.status,
                content_type=response.headers.get("Content-Type"),
                body=response.read(),
                error_class=None,
                error_message=None,
            )
    except urllib.error.HTTPError as exc:
        body = None
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001 - evidence best effort
            body = None
        return FetchResult(
            url=url,
            accept=accept,
            http_status=exc.code,
            content_type=exc.headers.get("Content-Type") if exc.headers else None,
            body=body,
            error_class="HTTP_ERROR",
            error_message=str(exc),
        )
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return FetchResult(
            url=url,
            accept=accept,
            http_status=None,
            content_type=None,
            body=None,
            error_class=type(exc).__name__,
            error_message=str(exc),
        )


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"schema": "regdelta.g0c.raw_manifest/v1", "entries": {}}


def save_manifest(manifest: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def capture(name: str, url: str, accept: str, extension: str) -> dict:
    """Fetch ``url`` and persist it as raw evidence under a stable logical name.

    The returned dict is the manifest entry. HTTP error bodies (e.g. the BOE
    API 404 XML) are captured too: the failure itself is part of the evidence.
    """
    result = fetch(url, accept)
    entry = {
        "name": name,
        "url": url,
        "accept": accept,
        "retrieved_at": now_utc_iso(),
        "http_status": result.http_status,
        "content_type": result.content_type,
        "error_class": result.error_class,
        "error_message": result.error_message,
        "sha256": None,
        "size_bytes": 0,
        "path": None,
    }
    if result.body is not None:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path = RAW_DIR / f"{name}.{extension}"
        path.write_bytes(result.body)
        entry["sha256"] = sha256_hex(result.body)
        entry["size_bytes"] = len(result.body)
        entry["path"] = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    manifest = load_manifest()
    manifest["entries"][name] = entry
    save_manifest(manifest)
    return entry


def read_raw(name: str) -> bytes:
    manifest = load_manifest()
    entry = manifest["entries"][name]
    return (REPO_ROOT / entry["path"]).read_bytes()


def read_raw_text(name: str) -> str:
    return read_raw(name).decode("utf-8", errors="replace")


def dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "ACCEPT_ANY",
    "ACCEPT_HTML",
    "ACCEPT_PDF",
    "ACCEPT_XML",
    "EVIDENCE_DIR",
    "FetchResult",
    "MANIFEST_PATH",
    "RAW_DIR",
    "REPO_ROOT",
    "asdict",
    "capture",
    "dump",
    "fetch",
    "load_manifest",
    "now_utc_iso",
    "read_raw",
    "read_raw_text",
    "save_manifest",
    "sha256_hex",
]
