"""跨实验复用的无平台依赖工具。"""

from .hashing import file_sha256, stable_text_hash
from .jsonl import DecodeReport, decode_json_records, iter_jsonl, read_jsonl

__all__ = [
    "DecodeReport",
    "decode_json_records",
    "file_sha256",
    "iter_jsonl",
    "read_jsonl",
    "stable_text_hash",
]
