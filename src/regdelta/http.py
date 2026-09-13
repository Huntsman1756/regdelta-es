from __future__ import annotations

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


@dataclass
class FetchResult:
    url: str
    http_status: int | None
    media_type: str | None
    body: bytes | None
    error_class: str | None
    error_message: str | None


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
                body = response.read()
                return FetchResult(
                    url=url,
                    http_status=response.status,
                    media_type=response.headers.get("Content-Type"),
                    body=body,
                    error_class=None,
                    error_message=None,
                )
        except urllib.error.HTTPError as exc:
            return FetchResult(
                url=url,
                http_status=exc.code,
                media_type=exc.headers.get("Content-Type") if exc.headers else None,
                body=None,
                error_class="HTTP_ERROR",
                error_message=str(exc),
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
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
