from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .util import sha256_hex


class BlobCollisionError(RuntimeError):
    pass


def blob_path(data_dir: Path, sha256: str) -> Path:
    if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError("sha256 must be exactly 64 lowercase hexadecimal characters")
    return Path(data_dir) / "raw" / "sha256" / sha256[:2] / sha256[2:4] / sha256


def store_blob(data_dir: Path, data: bytes) -> tuple[str, Path]:
    sha = sha256_hex(data)
    path = blob_path(Path(data_dir), sha)
    if path.exists():
        existing = path.read_bytes()
        if sha256_hex(existing) != sha:
            raise BlobCollisionError(f"file at {path} does not match its content address")
        return sha, path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".tmp-", dir=path.parent,
                                         delete=False) as fh:
            tmp = Path(fh.name)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return sha, path
