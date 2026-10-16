"""G0 — serving fidelity (plan §7.1). Statistics are implemented here; model-driven data collection is left to
the runner (``collect_*`` stubs document exactly what each test must produce)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np

from ..analysis.tost import chi2_homogeneity_p, paired_cluster_bootstrap_diff, tost_pass, tv_distance


@dataclass
class GateResult:
    name: str
    passed: bool
    details: Dict[str, float]


# ---------------------------------------------------------------- G0.3
def g0_3(kl_first_token: np.ndarray) -> GateResult:
    """kl_first_token: per-h_3 KL(cache-reuse || recompute) of the fp32 first-token distribution (nats)."""
    med, q95 = float(np.median(kl_first_token)), float(np.quantile(kl_first_token, 0.95))
    return GateResult("G0.3", med < 1e-3 and q95 < 1e-2, dict(delta_floor_median=med, delta_floor_q95=q95))


# ---------------------------------------------------------------- G0.4 / G0.5 / G0.8 (paired TOST)
def paired_tost_gate(name: str, e_a: np.ndarray, e_b: np.ndarray, cluster: np.ndarray, margin_pp: float,
                     extra_pass: bool = True, extra: Optional[Dict[str, float]] = None) -> GateResult:
    r = paired_cluster_bootstrap_diff(e_a, e_b, cluster, level=0.90)
    ok = tost_pass(r["lo"], r["hi"], margin_pp / 100.0) and extra_pass
    d = dict(diff=r["est"], ci90_lo=r["lo"], ci90_hi=r["hi"], n_clusters=r["n_clusters"], margin=margin_pp / 100.0)
    if extra:
        d.update(extra)
    return GateResult(name, ok, d)


def g0_4(e3_same_process: np.ndarray, e3_rebuilt: np.ndarray, y2_cluster: np.ndarray, ids_identical: bool,
         greedy_identical: bool, first_logit_maxdiff: float, text_path_mismatch_rate: float) -> GateResult:
    extra_ok = ids_identical and greedy_identical and first_logit_maxdiff < 1e-3 and text_path_mismatch_rate <= 0.01
    return paired_tost_gate("G0.4", e3_same_process, e3_rebuilt, y2_cluster, margin_pp=1.5, extra_pass=extra_ok,
                            extra=dict(first_logit_maxdiff=first_logit_maxdiff, text_path_mismatch_rate=text_path_mismatch_rate))


def g0_5(e3_batch1: np.ndarray, e3_batch8: np.ndarray, h3_cluster: np.ndarray, greedy_argmax_agreement: float) -> GateResult:
    return paired_tost_gate("G0.5", e3_batch1, e3_batch8, h3_cluster, margin_pp=1.5,
                            extra_pass=greedy_argmax_agreement >= 0.995, extra=dict(greedy_argmax_agreement=greedy_argmax_agreement))


def g0_8(e3_hf: np.ndarray, e3_vllm: np.ndarray, h3_cluster: np.ndarray) -> GateResult:
    return paired_tost_gate("G0.8", e3_hf, e3_vllm, h3_cluster, margin_pp=2.0)


# ---------------------------------------------------------------- G0.6
def g0_6(u3_hist_a: List[int], u3_hist_b: List[int], deterministic: bool, n_arms: int = 5) -> GateResult:
    if deterministic:
        ok = list(u3_hist_a) == list(u3_hist_b)
        return GateResult("G0.6", ok, dict(identical=float(ok)))
    ca = np.bincount(np.asarray(u3_hist_a), minlength=n_arms)
    cb = np.bincount(np.asarray(u3_hist_b), minlength=n_arms)
    tv, p = tv_distance(ca, cb), chi2_homogeneity_p(ca, cb)
    n_ok = min(len(u3_hist_a), len(u3_hist_b)) >= 20000
    return GateResult("G0.6", n_ok and tv < 0.02 and p > 0.01, dict(tv=tv, chi2_p=p, n=float(min(len(u3_hist_a), len(u3_hist_b)))))


# ---------------------------------------------------------------- G0.7
def g0_7(logp0_tokens: np.ndarray) -> GateResult:
    """logp0_tokens: log P^0 of every token of the steered responses under alpha=0 (fp32 log_softmax)."""
    defect = float(np.mean(np.asarray(logp0_tokens) < -60.0))
    return GateResult("G0.7", defect == 0.0, dict(support_defect=defect))


def write_gates_md(results: List[GateResult], path: str, run_id: str) -> None:
    lines = [f"## G0 — Serving 忠实性   run_id={run_id}", "", "| test | passed | details |", "| --- | --- | --- |"]
    for r in results:
        lines.append(f"| {r.name} | {'PASS' if r.passed else 'FAIL'} | {asdict(r)['details']} |")
    lines.append("")
    lines.append(f"Decision: {'GO' if all(r.passed for r in results) else 'STOP — fix pipeline'}")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
