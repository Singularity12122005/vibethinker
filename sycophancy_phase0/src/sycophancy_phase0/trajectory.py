"""Trajectory data model, ids hashing and the JSONL / z stores (plan §3, §5.5, §10.2).

Conventions fixed here (recorded as plan v1.3 clarifications):
* ``prefix_id(ids)`` = first 16 hex chars of SHA-256 over the decimal ids joined by ``","`` (language-independent).
* A trajectory's ``prefix_id`` is the hash of the ids fed to its **first generated turn** (``ids_1`` for a fresh
  trajectory, ``ids_2`` for D-prefill, ``ids_t`` for a continuation of a bank prefix ``h_t``).
* ``seeds[t-1]`` is ``null`` for turns that were inherited/prefilled rather than sampled by this trajectory.
* ``block``: ``"sel"`` iff ``trajectory_idx`` is even for G1 / G1.5 rollouts (``trajectory_idx < 64``);
  later gates pass ``block="est"`` explicitly with ``trajectory_idx >= 64``.
* ``subsplit = (trajectory_idx // 2) % 2`` and ``subsplit4 = (trajectory_idx // 2) % 4`` (plan §5.5).
* ``n_new_tokens = len(assistant_ids)`` (normalised ids, i.e. content tokens + the closing ``<|im_end|>``).
* z rows are stored fp16 unless a chunk contains a value above the fp16 range, in which case that chunk is fp32
  (the index records ``dtype``).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

from .constants import ACTION_GRID


def ids_hash(ids: Sequence[int], n_hex: int = 16) -> str:
    return hashlib.sha256(",".join(str(int(i)) for i in ids).encode()).hexdigest()[:n_hex]


def block_of(trajectory_idx: int) -> str:
    return "sel" if trajectory_idx % 2 == 0 else "est"


def subsplit_of(trajectory_idx: int) -> int:
    return (trajectory_idx // 2) % 2


def subsplit4_of(trajectory_idx: int) -> int:
    return (trajectory_idx // 2) % 4


# ---------------------------------------------------------------------- arm
@dataclass
class Arm:
    """Intervention vector in multiples of alpha_max (plan §3: u_t in {-1,-0.5,0,0.5,1})."""
    u: List[float]
    direction: Optional[str] = None
    layer: Optional[int] = None
    alpha_max: Optional[float] = None
    scope: Optional[str] = None
    fold_version: Optional[int] = None

    def __post_init__(self):
        self.u = [float(v) for v in self.u]
        for v in self.u:
            if not any(abs(v - g) < 1e-12 for g in ACTION_GRID):
                raise ValueError(f"u={v} not in action grid {ACTION_GRID}")
        if self.is_null:
            self.direction = self.layer = self.alpha_max = self.scope = self.fold_version = None
        else:
            if self.direction is None or self.layer is None or self.alpha_max is None or self.scope is None:
                raise ValueError("non-null arm needs direction, layer, alpha_max, scope")

    @property
    def is_null(self) -> bool:
        return all(v == 0.0 for v in self.u)

    @classmethod
    def null(cls, T: int = 4) -> "Arm":
        return cls(u=[0.0] * T)

    def alpha_at(self, t: int) -> float:
        """Absolute alpha (units of r_L) applied at turn t (1-based); 0 when the turn is beyond u."""
        if t - 1 >= len(self.u) or self.is_null:
            return 0.0
        return float(self.u[t - 1]) * float(self.alpha_max)

    def arm_id(self) -> str:
        """Canonical id used in seed derivation (plan §0.2 rule 3: seeds never shared across arms)."""
        if self.is_null:
            return "null"
        us = ",".join(f"{v:g}" for v in self.u)
        return f"u={us};dir={self.direction};L={self.layer};amax={self.alpha_max:g};scope={self.scope};fold={self.fold_version}"

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Arm":
        return cls(**d)


# ---------------------------------------------------------------------- turn / trajectory
@dataclass
class TurnRecord:
    t: int
    user_text: str
    ids_len_before: int                   # len(ids_t)  (prompt length for this turn)
    user_span: List[int]                  # [start, end) of x_t inside ids_t
    assistant_ids: List[int]              # normalised (ends with 151645)
    think_ids: Optional[List[int]]
    assistant_text: str
    finish_reason: str
    ended_with_endoftext: bool
    n_new_tokens: int
    source: str = "generated"             # generated | inherited | prefilled | external
    engine: Optional[str] = None          # hf | vllm | None
    alpha: float = 0.0                    # absolute alpha applied on this turn (0 for alpha=0 rollouts)
    prev_assistant_span: Optional[List[int]] = None   # [start, end) of y_{t-1} content tokens inside ids_t
    parsed: Optional[str] = None
    stance: Optional[str] = None
    explicit: Optional[str] = None
    judge: Optional[dict] = None
    judge2: Optional[dict] = None
    rule_stance: Optional[str] = None
    rule_conf: Optional[float] = None
    t4_format_miss: Optional[bool] = None
    truncated: bool = False
    truncated_in_think: bool = False
    no_think_close: bool = False
    stray_think_tokens: bool = False


@dataclass
class Trajectory:
    traj_id: str
    run_id: str
    config_sha256: str
    model: str
    regime: str
    problem_id: str
    family: str
    script: str
    prefix_id: str
    block: str
    trajectory_idx: int
    subsplit: int
    arm: Arm
    seeds: List[Optional[int]]
    turns: List[TurnRecord] = field(default_factory=list)
    outcomes: Optional[dict] = None
    z_rows: Optional[dict] = None
    truncated: bool = False
    truncated_in_think: bool = False
    timing_ms: Optional[float] = None
    subsplit4: int = 0
    mode: str = "instruct"
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["arm"] = self.arm.to_json()
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Trajectory":
        d = dict(d)
        d["arm"] = Arm.from_json(d["arm"])
        d["turns"] = [TurnRecord(**t) for t in d["turns"]]
        return cls(**d)


def traj_id_of(run_id: str, problem_id: str, prefix_id: str, arm_id: str, trajectory_idx: int) -> str:
    return hashlib.sha256("|".join([run_id, problem_id, prefix_id, arm_id, str(trajectory_idx)]).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------- stores
class JsonlWriter:
    """Append-only, one trajectory per line, flushed per write (crash-safe resume via traj_id)."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._f = open(path, "a", encoding="utf-8")

    def write(self, traj: Trajectory) -> None:
        self._f.write(json.dumps(traj.to_json(), ensure_ascii=False) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def read_jsonl(path: str) -> Iterable[Trajectory]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield Trajectory.from_json(json.loads(line))


def existing_traj_ids(paths: Sequence[str]) -> set:
    out = set()
    for p in paths:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        out.add(json.loads(line)["traj_id"])
    return out


class ZStore:
    """Rows per (traj, turn, layer, pool) in chunked ``.npy`` files with an index (plan §4.5).

    Layout: ``z/chunkNNNNN.npy`` of shape [n_rows, D]; the index maps (traj_id, turn, layer, pos) -> (path, row,
    dtype).  The index is JSONL (``z_index.jsonl``) and, when pyarrow is importable, also ``z_index.parquet``.
    """

    def __init__(self, root: str, chunk_rows: int = 4096):
        self.root = root
        os.makedirs(os.path.join(root, "z"), exist_ok=True)
        self.chunk_rows = chunk_rows
        self._buf: List[np.ndarray] = []
        self._buf_meta: List[dict] = []
        self._chunk = len([f for f in os.listdir(os.path.join(root, "z")) if f.endswith(".npy")])
        self._index_f = open(os.path.join(root, "z_index.jsonl"), "a", encoding="utf-8")

    def add(self, traj_id: str, turn: int, rows: Dict[str, Dict[int, np.ndarray]]) -> dict:
        """rows: {"R1": {layer: vec}, "R2": {...}, "R3": {...}} -> the z_rows reference dict for the JSONL."""
        ref: Dict[str, Dict[str, Dict[str, int]]] = {}
        for pos, by_layer in rows.items():
            for layer, vec in by_layer.items():
                row = sum(len(b) for b in self._buf)
                self._buf.append(np.asarray(vec, dtype=np.float32).reshape(1, -1))
                meta = dict(traj_id=traj_id, turn=int(turn), layer=int(layer), pos=pos, path=self._chunk_path(), row=row)
                self._buf_meta.append(meta)
                ref.setdefault(str(turn), {}).setdefault(pos, {})[str(layer)] = row
        if sum(len(b) for b in self._buf) >= self.chunk_rows:
            self.flush()
        return ref

    def _chunk_path(self) -> str:
        return os.path.join("z", f"chunk{self._chunk:05d}.npy")

    def flush(self) -> None:
        if not self._buf:
            return
        arr = np.concatenate(self._buf, 0).astype(np.float32)
        dtype = np.float16 if np.abs(arr).max() <= 65504.0 else np.float32   # plan §4.5 fp16; promote on overflow
        np.save(os.path.join(self.root, self._chunk_path()), arr.astype(dtype))
        for m in self._buf_meta:
            m["dtype"] = np.dtype(dtype).name
            self._index_f.write(json.dumps(m) + "\n")
        self._index_f.flush()
        self._buf, self._buf_meta = [], []
        self._chunk += 1

    def close(self) -> None:
        self.flush()
        self._index_f.close()
        try:
            import pyarrow.json as pj
            import pyarrow.parquet as pq
            tbl = pj.read_json(os.path.join(self.root, "z_index.jsonl"))
            pq.write_table(tbl, os.path.join(self.root, "z_index.parquet"))
        except Exception:
            pass

    @staticmethod
    def load_row(root: str, ref: dict) -> np.ndarray:
        return np.load(os.path.join(root, ref["path"]), mmap_mode="r")[ref["row"]]
