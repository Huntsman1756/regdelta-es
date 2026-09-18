from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 RegDelta/0.1"
)
TIMEOUT_SECONDS = 60
RETRIES_ON_NETWORK_ERROR = 1
MAX_BODY_BYTES = 128 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024

# Provenance of the observation itself. A source_check row records a real
# HTTP observation; replayed evidence bytes are provenance, not a new
# observation, and must never fabricate a check.
LIVE_FETCH = "LIVE_FETCH"
EVIDENCE_IMPORT = "EVIDENCE_IMPORT"


@dataclass
class FetchResult:
    url: str
    http_status: int | None
    media_type: str | None
    body: bytes | None
    error_class: str | None
    error_message: str | None
    via: str = LIVE_FETCH


class BodyTooLargeError(ValueError):
    pass


def _read_body(response) -> bytes:
    expected = None
    if not response.headers.get("Transfer-Encoding"):
        try:
            expected = int(response.headers.get("Content-Length", ""))
        except ValueError:
            pass
    if expected is not None and expected < 0:
        expected = None
    if response.status in (204, 304):
        expected = None
    if expected is not None and expected > MAX_BODY_BYTES:
        raise BodyTooLargeError(f"response body exceeds {MAX_BODY_BYTES} bytes")
    body = bytearray()
    while True:
        chunk = response.read(min(READ_CHUNK_BYTES, MAX_BODY_BYTES + 1 - len(body)))
        if not chunk:
            break
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise BodyTooLargeError(f"response body exceeds {MAX_BODY_BYTES} bytes")
        body.extend(chunk)
    if expected is not None and len(body) < expected:
        raise http.client.IncompleteRead(bytes(body), expected - len(body))
    return bytes(body)


def http_fetch(url: str, accept: str = "*/*") -> FetchResult:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "es-ES,es;q=0.9",
    }
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1 + RETRIES_ON_NETWORK_ERROR):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = _read_body(response)
                return FetchResult(
                    url=url,
                    http_status=response.status,
                    media_type=response.headers.get("Content-Type"),
                    body=body,
                    error_class=None,
                    error_message=None,
                )
        except BodyTooLargeError as exc:
            return FetchResult(
                url=url,
                http_status=None,
                media_type=None,
                body=None,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
        except urllib.error.HTTPError as exc:
            try:
                return FetchResult(
                    url=url,
                    http_status=exc.code,
                    media_type=exc.headers.get("Content-Type") if exc.headers else None,
                    body=None,
                    error_class="HTTP_ERROR",
                    error_message=str(exc),
                )
            finally:
                exc.close()
        except (http.client.HTTPException, urllib.error.URLError, TimeoutError,
                ConnectionError, OSError) as exc:
            if attempt < RETRIES_ON_NETWORK_ERROR:
                time.sleep(2)
                continue
            return FetchResult(
                url=url,
                http_status=None,
                media_type=None,
                body=None,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
    raise AssertionError("unreachable")
