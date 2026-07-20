"""Hashing helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:12]


def content_hash(content: str | bytes) -> str:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:12]
