"""稳定文本与文件摘要。"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path


def normalize_text(text: str, *, casefold: bool = True) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = " ".join(value.split())
    return value.casefold() if casefold else value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_text_hash(text: str, *, casefold: bool = True) -> str:
    return sha256_text(normalize_text(text, casefold=casefold))


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
