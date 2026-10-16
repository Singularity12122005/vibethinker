"""Controller interface contract (plan §0.2 rule 7, §7.1 G0.6).

``policy(ids_t, z_t, t, rng) -> u_t`` with ``u_t`` in ``ACTION_GRID`` (multiples of alpha_max).  The policy must not
read u_{<t}, must not carry a running budget, and must use ``rng`` as its only source of randomness.  ``ids_t`` is the
full token-id prefix fed to turn t (a text state); ``z_t`` the §4.5 features for that prefix (or None).

``contract_check`` runs a policy through two different turn-1/2 *histories* that end in the identical ``ids_3``:
a contract-abiding deterministic policy returns identical u_3; a random one returns the same u_3 distribution.
"""
from __future__ import annotations

import random
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .constants import ACTION_GRID
from .inference.sampling import derive_seed
from .trajectory import ids_hash

Policy = Callable[[Sequence[int], Optional[np.ndarray], int, random.Random], float]


def action_index(u: float) -> int:
    for i, g in enumerate(ACTION_GRID):
        if abs(float(u) - g) < 1e-9:
            return i
    raise ValueError(f"u={u} not in {ACTION_GRID}")


def policy_rng(run_id: str, problem_id: str, prefix_id: str, trajectory_idx: int, t: int) -> random.Random:
    """Per-turn controller RNG, derived like the sampling seeds but under the reserved arm id 'policy'."""
    return random.Random(derive_seed(run_id, problem_id, prefix_id, "policy", trajectory_idx, t))


# ---------------------------------------------------------------- placeholders
def deterministic_placeholder(ids_t: Sequence[int], z_t, t: int, rng: random.Random) -> float:
    """Depends on the text state only (hash of ids_t)."""
    return ACTION_GRID[int(ids_hash(ids_t), 16) % len(ACTION_GRID)]


def random_placeholder(ids_t: Sequence[int], z_t, t: int, rng: random.Random) -> float:
    return rng.choice(ACTION_GRID)


def open_loop(schedule: Sequence[float]) -> Policy:
    """alpha*(t): fixed per-turn schedule (G7 baseline)."""
    def pol(ids_t, z_t, t, rng):
        return float(schedule[t - 1]) if t - 1 < len(schedule) else 0.0
    return pol


class StatefulCheater:
    """Violates the contract on purpose (tests): its answer depends on the ids of the *previous* call, i.e. on the
    history u_{<t} shaped, which the signature forbids reading."""

    def __init__(self):
        self.prev_ids = None

    def __call__(self, ids_t, z_t, t, rng):
        key = ids_hash(self.prev_ids) if self.prev_ids is not None else "0"
        self.prev_ids = list(ids_t)
        return ACTION_GRID[int(key, 16) % len(ACTION_GRID)]


# ---------------------------------------------------------------- G0.6
History = Sequence[Tuple[Sequence[int], Optional[np.ndarray]]]   # [(ids_1, z_1), (ids_2, z_2)] of one history


def contract_check(policy: Policy, ids_3: Sequence[int], z_3, histories: Sequence[History], *, n: int,
                   deterministic: bool, seed: int = 20261016) -> List[List[int]]:
    """For each history: replay the policy on the history's turn-1/2 states, then on the shared ``ids_3``; return
    the action indices of u_3 per history (``n`` repetitions).  Deterministic policies get the *same* rng seeds
    across histories (exact equality expected); random ones get different streams per history (TV / χ² test)."""
    out: List[List[int]] = []
    for h_idx, hist in enumerate(histories):
        u3s: List[int] = []
        for i in range(n):
            base = seed + i if deterministic else seed + i + 1_000_003 * (h_idx + 1)
            for t, (ids_t, z_t) in enumerate(hist, start=1):
                policy(ids_t, z_t, t, random.Random(base * 10 + t))
            u = policy(ids_3, z_3, len(hist) + 1, random.Random(base * 10 + len(hist) + 1))
            u3s.append(action_index(u))
        out.append(u3s)
    return out
