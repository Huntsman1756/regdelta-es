from __future__ import annotations

import os
import time
from pathlib import Path

from .util import sha256_hex


class BlobCollisionError(RuntimeError):
    pass


def blob_path(data_dir: Path, sha256: str) -> Path:
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
    tmp = path.with_name(f".tmp-{os.getpid()}-{time.time_ns()}")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return sha, path
