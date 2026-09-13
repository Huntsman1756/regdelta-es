from __future__ import annotations

import pytest

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
