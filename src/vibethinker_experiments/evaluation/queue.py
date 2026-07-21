"""Small resumable file queue and deterministic shard merge contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .io import index_unique, read_jsonl, write_json


class WorkQueue:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.pending = self.root / "pending"
        self.running = self.root / "running"
        self.done = self.root / "done"

    def initialize(self, rows: list[dict[str, Any]]) -> None:
        for directory in (self.pending, self.running, self.done):
            directory.mkdir(parents=True, exist_ok=True)
        indexed = index_unique(rows, "panel_id")
        for panel_id, row in sorted(indexed.items()):
            item_name = hashlib.sha256(panel_id.encode()).hexdigest() + ".json"
            path = self.pending / item_name
            if not path.exists() and not (self.done / path.name).exists():
                write_json(path, row)

    def recover(self) -> None:
        """Return abandoned claims to pending without duplicating completed work."""

        for claimed in sorted(self.running.glob("*.json")):
            name = claimed.name.split(".", 1)[-1]
            destination = self.pending / name
            if (self.done / name).exists():
                claimed.unlink()
            elif destination.exists():
                claimed.unlink()
            else:
                claimed.replace(destination)

    def claim(self, worker_id: str) -> tuple[Path, dict[str, Any]] | None:
        if not worker_id or any(char not in "._-" and not char.isalnum() for char in worker_id):
            raise ValueError("worker_id contains unsafe characters")
        worker_token = hashlib.sha256(worker_id.encode()).hexdigest()[:16]
        for pending in sorted(self.pending.glob("*.json")):
            claimed = self.running / f"{worker_token}.{pending.name}"
            try:
                os.replace(pending, claimed)
            except FileNotFoundError:
                continue
            value = json.loads(claimed.read_text())
            if not isinstance(value, dict):
                raise ValueError(f"{claimed}: queue item must be an object")
            return claimed, value
        return None

    def complete(self, claimed: Path) -> None:
        name = claimed.name.split(".", 1)[-1]
        destination = self.done / name
        if destination.exists():
            claimed.unlink(missing_ok=True)
            return
        claimed.replace(destination)

    def state(self) -> dict[str, int]:
        return {
            "pending": len(list(self.pending.glob("*.json"))),
            "running": len(list(self.running.glob("*.json"))),
            "done": len(list(self.done.glob("*.json"))),
        }


def merge_result_shards(
    panel_rows: list[dict[str, Any]], shard_paths: list[str | Path]
) -> list[dict[str, Any]]:
    expected = [str(row["panel_id"]) for row in panel_rows]
    merged: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(value) for value in shard_paths):
        for row in read_jsonl(path):
            panel_id = str(row.get("panel_id", ""))
            if panel_id in merged:
                raise ValueError(f"duplicate result for {panel_id}")
            merged[panel_id] = row
    missing = [panel_id for panel_id in expected if panel_id not in merged]
    extra = sorted(set(merged) - set(expected))
    if missing or extra:
        raise ValueError(f"result coverage mismatch: missing={missing} extra={extra}")
    return [merged[panel_id] for panel_id in expected]
