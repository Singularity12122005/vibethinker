"""Small, audited extensions for the Skywork-OR1/DAPO training recipe."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from math import gcd


@dataclass
class AdaptiveEntropyController:
    """Skywork-OR1's bounded additive entropy-coefficient controller."""

    value: float = 0.0
    target_entropy: float = 0.2
    min_value: float = 0.0
    max_value: float = 0.005
    delta: float = 0.0001
    loss_enabled: bool = True

    def update(self, entropy: float) -> None:
        self.value += self.delta if entropy < self.target_entropy else -self.delta
        self.value = min(self.max_value, max(self.min_value, self.value))
        self.loss_enabled = entropy < self.target_entropy

    @property
    def realized_value(self) -> float:
        return self.value if self.loss_enabled else 0.0

    def state_dict(self) -> dict[str, float | bool]:
        return asdict(self)

    def load_state_dict(self, state: dict[str, float | bool]) -> None:
        expected = set(self.state_dict())
        if set(state) != expected:
            raise ValueError(f"adaptive entropy state keys mismatch: {set(state)} != {expected}")
        for key, value in state.items():
            setattr(self, key, bool(value) if key == "loss_enabled" else float(value))


def select_nonconstant_group_indices(
    uids: Sequence[object],
    scores: Sequence[float],
    *,
    group_size: int,
    world_size: int,
) -> tuple[list[int], dict[str, float | int]]:
    """Drop constant binary-reward groups and preserve dispatchable GRPO groups."""

    if len(uids) != len(scores):
        raise ValueError("uids and scores must have equal length")
    if group_size < 2 or world_size < 1:
        raise ValueError("group_size must be >=2 and world_size must be positive")

    groups: dict[object, list[int]] = {}
    for index, uid in enumerate(uids):
        groups.setdefault(uid, []).append(index)

    valid_groups: list[tuple[object, list[int]]] = []
    all_zero = 0
    all_one = 0
    for uid, indices in groups.items():
        if len(indices) != group_size:
            raise ValueError(f"incomplete GRPO group: expected {group_size}, got {len(indices)}")
        group_scores = [float(scores[index]) for index in indices]
        if any(score not in (0.0, 1.0) for score in group_scores):
            raise ValueError(f"binary reward violated: {group_scores}")
        if all(score == 0.0 for score in group_scores):
            all_zero += 1
        elif all(score == 1.0 for score in group_scores):
            all_one += 1
        else:
            valid_groups.append((uid, indices))

    groups_per_dispatch_block = world_size // gcd(world_size, group_size)
    valid_groups.sort(key=lambda item: hashlib.sha256(str(item[0]).encode()).digest())
    usable_count = len(valid_groups) - len(valid_groups) % groups_per_dispatch_block
    dropped_for_dispatch = len(valid_groups) - usable_count
    selected = [index for _, indices in valid_groups[:usable_count] for index in indices]
    total_groups = len(groups)
    stats: dict[str, float | int] = {
        "group_filter/total": total_groups,
        "group_filter/all_zero": all_zero,
        "group_filter/all_one": all_one,
        "group_filter/nonconstant_before_alignment": len(valid_groups),
        "group_filter/dropped_for_dispatch": dropped_for_dispatch,
        "group_filter/kept": usable_count,
        "group_filter/kept_ratio": usable_count / total_groups if total_groups else 0.0,
    }
    return selected, stats


def filter_parallel_values(values: Iterable[object], indices: Sequence[int]) -> list[object]:
    materialized = list(values)
    return [materialized[index] for index in indices]
