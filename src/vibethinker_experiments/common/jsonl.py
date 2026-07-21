"""JSON/JSONL 解码。

这里不假设“一行一条记录”，因此支持格式化的多行 JSON、相邻 JSON 值和
顶层数组。JSON 字符串中的未转义换行本身不合法，不能被无损恢复；损坏值会
被计数并跳到下一行继续，而不会伪造或静默修补数据。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DecodeReport:
    records: list[dict[str, Any]]
    malformed_segments: int = 0
    non_object_values: int = 0


def decode_json_records(text: str) -> DecodeReport:
    """解码对象流，并将顶层对象数组展开为记录。"""
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    malformed = non_objects = 0
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset >= len(text):
            break
        try:
            value, end = decoder.raw_decode(text, offset)
        except json.JSONDecodeError:
            malformed += 1
            next_line = text.find("\n", offset)
            if next_line < 0:
                break
            offset = next_line + 1
            continue
        offset = end
        if isinstance(value, dict):
            records.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
                else:
                    non_objects += 1
        else:
            non_objects += 1
    return DecodeReport(records, malformed, non_objects)


def read_jsonl(path: str | Path, *, strict: bool = False) -> list[dict[str, Any]]:
    """读取记录；strict 模式拒绝任何损坏片段或非对象值。"""
    report = decode_json_records(Path(path).read_text(encoding="utf-8", errors="replace"))
    if strict and (report.malformed_segments or report.non_object_values):
        raise ValueError(
            f"{path}: malformed={report.malformed_segments}, non_object={report.non_object_values}"
        )
    return report.records


def iter_jsonl(path: str | Path, *, strict: bool = False) -> Iterator[dict[str, Any]]:
    yield from read_jsonl(path, strict=strict)


def encode_jsonl(rows: Iterable[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    )
