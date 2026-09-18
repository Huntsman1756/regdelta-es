from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from regdelta import rawstore
from regdelta.rawstore import BlobCollisionError, blob_path, store_blob
from regdelta.util import sha256_hex


def test_store_blob_path_and_identity(fresh_dir):
    data = b"official bytes"
    sha, path = store_blob(fresh_dir, data)
    assert sha == sha256_hex(data)
    expected = fresh_dir / "raw" / "sha256" / sha[:2] / sha[2:4] / sha
    assert path == expected
    assert path.read_bytes() == data


def test_store_blob_is_extensionless(fresh_dir):
    _, path = store_blob(fresh_dir, b"data")
    assert path.suffix == ""


def test_reput_does_not_rewrite(fresh_dir):
    data = b"same bytes"
    _, path = store_blob(fresh_dir, data)
    before = path.stat().st_mtime_ns
    sha2, path2 = store_blob(fresh_dir, data)
    after = path.stat().st_mtime_ns
    assert sha2 == sha256_hex(data)
    assert path2 == path
    assert before == after


def test_corrupted_content_address_raises(fresh_dir):
    data = b"original"
    _, path = store_blob(fresh_dir, data)
    path.write_bytes(b"tampered")
    with pytest.raises(BlobCollisionError):
        store_blob(fresh_dir, data)


def test_orphan_detection_helper(fresh_dir):
    data = b"orphan candidate"
    sha, path = store_blob(fresh_dir, data)
    assert blob_path(fresh_dir, sha) == path
    assert path.exists()


@pytest.mark.parametrize("digest", [
    "", "a" * 63, "a" * 65, "A" * 64, "g" * 64,
    "a" * 63 + "\n", " " + "a" * 64, "a" * 64 + " ",
    None, 123, b"a" * 64,
])
def test_blob_path_rejects_invalid_digest_before_path_construction(digest):
    class UnusablePath:
        def __fspath__(self):
            raise AssertionError("path constructed before validation")

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        blob_path(UnusablePath(), digest)


@pytest.mark.parametrize("digest", ["0" * 64, "abcdef0123456789" * 4])
def test_blob_path_accepts_lowercase_hex(fresh_dir, digest):
    assert blob_path(fresh_dir, digest) == (
        fresh_dir / "raw" / "sha256" / digest[:2] / digest[2:4] / digest
    )


@pytest.mark.parametrize("data", [b"", b"official bytes", bytes(range(256))])
def test_secure_temporary_write_order_and_cleanup(fresh_dir, monkeypatch, data):
    expected = blob_path(fresh_dir, sha256_hex(data))
    temporary_file = rawstore.tempfile.NamedTemporaryFile
    fsync = os.fsync
    replace = os.replace
    events = []
    handles = []

    def create(**kwargs):
        assert kwargs == {"mode": "wb", "prefix": ".tmp-", "dir": expected.parent, "delete": False}
        handle = temporary_file(**kwargs)
        handles.append(handle)
        assert Path(handle.name).parent == expected.parent
        assert Path(handle.name) != expected
        with pytest.raises(FileExistsError):
            open(handle.name, "xb")
        events.append("create")
        return handle

    def sync(fd):
        assert not handles[0].closed
        assert Path(handles[0].name).read_bytes() == data
        events.append("fsync")
        fsync(fd)

    def publish(source, destination):
        assert handles[0].closed
        assert source == Path(handles[0].name)
        assert destination == expected
        assert not destination.exists()
        events.append("replace")
        replace(source, destination)

    monkeypatch.setattr(rawstore.tempfile, "NamedTemporaryFile", create)
    monkeypatch.setattr(rawstore.os, "fsync", sync)
    monkeypatch.setattr(rawstore.os, "replace", publish)
    sha, path = store_blob(fresh_dir, data)
    assert sha == sha256_hex(data)
    assert path == expected
    assert path.read_bytes() == data
    assert events == ["create", "fsync", "replace"]
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("stage", ["create", "write", "flush", "fsync", "replace"])
def test_failed_write_cleans_temporary_file(fresh_dir, monkeypatch, stage):
    data = b"official bytes"
    path = blob_path(fresh_dir, sha256_hex(data))
    path.parent.mkdir(parents=True)
    unrelated = path.parent / ".tmp-existing"
    unrelated.write_bytes(b"unchanged")
    temporary_file = rawstore.tempfile.NamedTemporaryFile
    failure = OSError("injected storage failure")
    handles = []

    class FailingFile:
        def __init__(self, handle):
            self.handle = handle
            self.name = handle.name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def write(self, value):
            if stage == "write":
                self.handle.write(value[:3])
                raise failure
            return self.handle.write(value)

        def flush(self):
            if stage == "flush":
                raise failure
            return self.handle.flush()

        def fileno(self):
            return self.handle.fileno()

    def create(**kwargs):
        if stage == "create":
            raise failure
        handle = temporary_file(**kwargs)
        handles.append(handle)
        return FailingFile(handle)

    monkeypatch.setattr(rawstore.tempfile, "NamedTemporaryFile", create)
    if stage in ("fsync", "replace"):
        monkeypatch.setattr(rawstore.os, stage, Mock(side_effect=failure))
    with pytest.raises(OSError, match="injected storage failure"):
        store_blob(fresh_dir, data)
    assert all(handle.closed for handle in handles)
    assert not path.exists()
    assert list(path.parent.iterdir()) == [unrelated]
    assert unrelated.read_bytes() == b"unchanged"


def test_existing_blob_never_creates_temporary_file(fresh_dir, monkeypatch):
    data = b"official bytes"
    expected = store_blob(fresh_dir, data)
    create = Mock(side_effect=AssertionError("unexpected temporary file"))
    monkeypatch.setattr(rawstore.tempfile, "NamedTemporaryFile", create)
    assert store_blob(fresh_dir, data) == expected
    create.assert_not_called()
