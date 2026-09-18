from __future__ import annotations

from http import client
import io
import urllib.error
from email.message import Message
from unittest.mock import Mock

import pytest

from regdelta import http

URL = "https://example.invalid/document"


class Response(io.BytesIO):
    def __init__(self, body=b"official bytes", status=200, headers=None, short_read=None):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self.short_read = short_read
        self.read_sizes = []
        self.bytes_read = 0

    def read(self, size=-1):
        assert 0 < size <= http.READ_CHUNK_BYTES
        self.read_sizes.append(size)
        result = super().read(min(size, self.short_read) if self.short_read else size)
        self.bytes_read += len(result)
        return result


@pytest.fixture(autouse=True)
def transport(monkeypatch):
    opener = Mock(side_effect=AssertionError("unexpected request"))
    sleep = Mock()
    monkeypatch.setattr(http.urllib.request, "urlopen", opener)
    monkeypatch.setattr(http.time, "sleep", sleep)
    return opener, sleep


@pytest.mark.parametrize("status,body", [(200, b"official bytes"), (201, b"created"), (204, b"")])
def test_success_shape_headers_and_close(transport, status, body):
    opener, sleep = transport
    response = Response(body, status, {"Content-Type": "text/plain", "Content-Length": str(len(body))})
    opener.side_effect = [response]
    result = http.http_fetch(URL, "text/plain")
    assert result == http.FetchResult(URL, status, "text/plain", body, None, None)
    assert result.via == http.LIVE_FETCH
    request = opener.call_args.args[0]
    assert request.full_url == URL
    assert request.get_header("Accept") == "text/plain"
    assert request.get_header("User-agent") == http.USER_AGENT
    assert request.get_header("Accept-language") == "es-ES,es;q=0.9"
    assert opener.call_args.kwargs == {"timeout": 60}
    assert response.closed
    sleep.assert_not_called()


@pytest.mark.parametrize("status", [304, 404, 500])
@pytest.mark.parametrize("with_headers", [False, True])
def test_http_error_closed_without_read_or_retry(transport, status, with_headers):
    opener, sleep = transport
    stream = Response()
    headers = Message() if with_headers else None
    if headers is not None:
        headers["Content-Type"] = "text/plain"
    error = urllib.error.HTTPError(URL, status, "status response", headers, stream)
    opener.side_effect = error
    result = http.http_fetch(URL)
    assert result == http.FetchResult(
        URL, status, "text/plain" if with_headers else None, None, "HTTP_ERROR", str(error)
    )
    assert stream.closed
    assert stream.read_sizes == []
    assert opener.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("error_type", [
    urllib.error.URLError, TimeoutError, ConnectionError, OSError,
    client.HTTPException, client.RemoteDisconnected,
])
@pytest.mark.parametrize("recover", [False, True])
def test_network_retry(transport, error_type, recover):
    opener, sleep = transport
    error = error_type("connection interrupted")
    response = Response()
    opener.side_effect = [error, response if recover else error]
    result = http.http_fetch(URL)
    assert opener.call_count == 2
    sleep.assert_called_once_with(2)
    if recover:
        assert result.body == b"official bytes"
        assert result.error_class is None
        assert response.closed
    else:
        assert result == http.FetchResult(URL, None, None, None, error_type.__name__, str(error))


@pytest.mark.parametrize("recover", [False, True])
def test_incomplete_read_discards_partial_and_retries(transport, recover):
    opener, sleep = transport
    first = Response()
    second = Response()
    first.read = Mock(side_effect=client.IncompleteRead(b"part", 10))
    if not recover:
        second.read = Mock(side_effect=client.IncompleteRead(b"part", 10))
    opener.side_effect = [first, second]
    result = http.http_fetch(URL)
    assert first.closed and second.closed
    assert opener.call_count == 2
    sleep.assert_called_once_with(2)
    assert result.body == (b"official bytes" if recover else None)
    assert result.error_class == (None if recover else "IncompleteRead")


@pytest.mark.parametrize("recover", [False, True])
def test_content_length_truncation(transport, recover):
    opener, sleep = transport
    first = Response(b"part", headers={"Content-Length": "8"}, short_read=2)
    second = Response(b"complete" if recover else b"part", headers={"Content-Length": "8"})
    opener.side_effect = [first, second]
    result = http.http_fetch(URL)
    assert first.closed and second.closed
    assert first.bytes_read == 4
    assert result.body == (b"complete" if recover else None)
    assert result.error_class == (None if recover else "IncompleteRead")
    sleep.assert_called_once_with(2)


@pytest.mark.parametrize("length", [None, "8", "not specified", "-1"])
def test_exact_limit_with_short_reads(transport, monkeypatch, length):
    opener, sleep = transport
    monkeypatch.setattr(http, "MAX_BODY_BYTES", 8)
    headers = {} if length is None else {"Content-Length": length}
    response = Response(b"12345678", headers=headers, short_read=3)
    opener.side_effect = [response]
    result = http.http_fetch(URL)
    assert result.body == b"12345678"
    assert result.error_class is None
    assert response.closed
    assert response.read_sizes[-1] == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("length,expected_read", [(None, 9), ("12", 0), ("8", 9)])
def test_over_limit_returns_no_partial_body(transport, monkeypatch, length, expected_read):
    opener, sleep = transport
    monkeypatch.setattr(http, "MAX_BODY_BYTES", 8)
    headers = {} if length is None else {"Content-Length": length}
    response = Response(b"ordinary data", headers=headers)
    opener.side_effect = [response]
    result = http.http_fetch(URL)
    assert result.body is None
    assert result.error_class == "BodyTooLargeError"
    assert result.error_message == "response body exceeds 8 bytes"
    assert response.bytes_read == expected_read
    assert response.closed
    assert opener.call_count == 1
    sleep.assert_not_called()


def test_default_resource_limits_and_chunking(transport):
    opener, _ = transport
    assert http.MAX_BODY_BYTES == 134217728
    assert http.READ_CHUNK_BYTES == 65536
    assert http.TIMEOUT_SECONDS == 60
    assert http.RETRIES_ON_NETWORK_ERROR == 1
    body = b"a" * (http.READ_CHUNK_BYTES + 17)
    response = Response(body)
    opener.side_effect = [response]
    assert http.http_fetch(URL).body == body
    assert response.read_sizes == [65536, 65536, 65536]
    assert response.closed


@pytest.mark.parametrize("status,headers", [
    (204, {"Content-Length": "10"}),
    (304, {"Content-Length": "10"}),
    (200, {"Transfer-Encoding": "chunked", "Content-Length": "10"}),
])
def test_content_length_not_used_when_inapplicable(transport, status, headers):
    opener, _ = transport
    response = Response(b"", status=status, headers=headers)
    opener.side_effect = [response]
    result = http.http_fetch(URL)
    assert result.body == b""
    assert result.error_class is None
    assert response.closed
