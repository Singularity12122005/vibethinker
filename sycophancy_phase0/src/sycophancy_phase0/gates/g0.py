"""G0 — serving fidelity (plan §7.1): decision statistics and the GATES.md writer (§7.0).

Model-driven data collection lives in ``gates/g0_runner.py``; this module turns its outputs into GateResults.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..analysis.tost import chi2_homogeneity_p, paired_cluster_bootstrap_diff, tost_pass, tv_distance

DECISIONS = ("GO", "GO-with-caveat", "KILL", "GREY")
G0_TESTS = ("G0.1", "G0.2", "G0.3", "G0.4", "G0.5", "G0.6", "G0.7", "G0.8")


@dataclass
class GateResult:
    name: str
    passed: bool
    details: Dict[str, object]
    criteria: str = ""              # pre-registered criterion text (verbatim from the plan)
    inputs: str = ""
    notes: str = ""

    def results_text(self) -> str:
        return "; ".join(f"{k}={_fmt(v)}" for k, v in self.details.items())


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


# ---------------------------------------------------------------- G0.1 / G0.2
def g0_1(n_mismatch: int, n_total: int) -> GateResult:
    rate = n_mismatch / n_total if n_total else float("nan")
    return GateResult("G0.1", n_total > 0 and rate <= 0.01, dict(mismatch_rate=rate, n=n_total),
                      criteria="模板一致性：id 拼接与 apply_chat_template 文本路径逐位比较，不一致率 ≤1%")


def g0_2(checks: Dict[str, bool], sampler_chi2_p: float) -> GateResult:
    """checks: the §4.4 self-checks + processor-list check, all must be True; sampler χ² p>0.01 (§4.3)."""
    d: Dict[str, object] = {k: bool(v) for k, v in checks.items()}
    d["sampler_chi2_p"] = float(sampler_chi2_p)
    ok = all(bool(v) for v in checks.values()) and sampler_chi2_p > 0.01
    return GateResult("G0.2", ok, d, criteria="§4.4 四项 hook 自检、processor 列表不含 TemperatureLogitsWarper、首 token χ² p>0.01：全部通过")


# ---------------------------------------------------------------- G0.3
def g0_3(kl_first_token: np.ndarray) -> GateResult:
    """kl_first_token: per-h_3 KL(cache-reuse || recompute) of the fp32 first-token distribution (nats)."""
    med, q95 = float(np.median(kl_first_token)), float(np.quantile(kl_first_token, 0.95))
    return GateResult("G0.3", med < 1e-3 and q95 < 1e-2, dict(delta_floor_median=med, delta_floor_q95=q95, n=len(kl_first_token)),
                      criteria="首 token fp32 log_softmax 的 KL：中位数 <1e-3 nats，95% 分位 <1e-2；记录为 delta_floor")


# ---------------------------------------------------------------- paired TOST gates
def paired_tost_gate(name: str, e_a: np.ndarray, e_b: np.ndarray, cluster: np.ndarray, margin_pp: float,
                     extra_pass: bool = True, extra: Optional[Dict[str, object]] = None, criteria: str = "") -> GateResult:
    r = paired_cluster_bootstrap_diff(e_a, e_b, cluster, level=0.90)
    ok = tost_pass(r["lo"], r["hi"], margin_pp / 100.0) and extra_pass
    d: Dict[str, object] = dict(diff=r["est"], ci90_lo=r["lo"], ci90_hi=r["hi"], n_clusters=r["n_clusters"], margin=margin_pp / 100.0)
    if extra:
        d.update(extra)
    return GateResult(name, ok, d, criteria=criteria)


def g0_4(e3_same_process: np.ndarray, e3_rebuilt: np.ndarray, y2_cluster: np.ndarray, ids_identical: bool,
         greedy_identical: bool, first_logit_maxdiff: float, text_path_mismatch_rate: float) -> GateResult:
    extra_ok = ids_identical and greedy_identical and first_logit_maxdiff < 1e-3 and text_path_mismatch_rate <= 0.01
    return paired_tost_gate("G0.4", e3_same_process, e3_rebuilt, y2_cluster, margin_pp=1.5, extra_pass=extra_ok,
                            extra=dict(ids_identical=ids_identical, greedy_identical=greedy_identical,
                                       first_logit_maxdiff=first_logit_maxdiff, text_path_mismatch_rate=text_path_mismatch_rate),
                            criteria="(i)(ii) ids_3 逐位相同、greedy 续写逐 token 相同、首 token logits max|Δ|<1e-3；(ii)(iii) 不一致率 ≤1%；"
                                     "e_3 率差的配对 cluster bootstrap 90% CI ⊂ (−1.5, 1.5)pp")


def g0_5(e3_batch1: np.ndarray, e3_batch8: np.ndarray, e3_grouped: np.ndarray, h3_cluster: np.ndarray,
         greedy_argmax_agreement: float) -> GateResult:
    """Three batch conditions (batch=1 / batch=8 random peers / grouped by arm): both contrasts vs batch=1 must pass."""
    r1 = paired_cluster_bootstrap_diff(e3_batch1, e3_batch8, h3_cluster, level=0.90)
    r2 = paired_cluster_bootstrap_diff(e3_batch1, e3_grouped, h3_cluster, level=0.90)
    ok = (tost_pass(r1["lo"], r1["hi"], 0.015) and tost_pass(r2["lo"], r2["hi"], 0.015) and greedy_argmax_agreement >= 0.995)
    return GateResult("G0.5", ok, dict(diff_b1_b8=r1["est"], ci90_b1_b8=(r1["lo"], r1["hi"]), diff_b1_grouped=r2["est"],
                                       ci90_b1_grouped=(r2["lo"], r2["hi"]), greedy_argmax_agreement=greedy_argmax_agreement,
                                       n_clusters=r1["n_clusters"]),
                      criteria="greedy argmax 一致率 ≥99.5%；三种 batch 条件两两（相对 batch=1）e_3 率差配对 cluster bootstrap 90% CI ⊂ (−1.5, 1.5)pp")


def g0_8(e3_hf: np.ndarray, e3_vllm: np.ndarray, h3_cluster: np.ndarray, steered: Optional[dict] = None) -> GateResult:
    r = paired_tost_gate("G0.8", e3_hf, e3_vllm, h3_cluster, margin_pp=2.0,
                         criteria="HF vs vLLM α=0 各 128 条配对续写：e_3 率差配对 cluster bootstrap 90% CI ⊂ (−2, 2)pp")
    if steered is not None:
        rs = paired_cluster_bootstrap_diff(steered["e3_hf"], steered["e3_vllm"], steered["cluster"], level=0.90)
        r.details.update(steered_diff=rs["est"], steered_ci90=(rs["lo"], rs["hi"]))
        r.passed = r.passed and tost_pass(rs["lo"], rs["hi"], 0.02)
    return r


# ---------------------------------------------------------------- G0.6
def g0_6(u3_hist_a: Sequence[int], u3_hist_b: Sequence[int], deterministic: bool, n_arms: int = 5) -> GateResult:
    crit = "确定性：u_3 逐位相同；随机：各 n≥20000，5 臂频率 TV<0.02 且 χ² p>0.01"
    if deterministic:
        ok = list(u3_hist_a) == list(u3_hist_b)
        return GateResult("G0.6", ok, dict(identical=ok, n=len(u3_hist_a)), criteria=crit)
    ca = np.bincount(np.asarray(u3_hist_a), minlength=n_arms)
    cb = np.bincount(np.asarray(u3_hist_b), minlength=n_arms)
    tv, p = tv_distance(ca, cb), chi2_homogeneity_p(ca, cb)
    n = min(len(u3_hist_a), len(u3_hist_b))
    return GateResult("G0.6", n >= 20000 and tv < 0.02 and p > 0.01, dict(tv=tv, chi2_p=p, n=n), criteria=crit)


# ---------------------------------------------------------------- G0.7
def g0_7(logp0_tokens: np.ndarray) -> GateResult:
    """logp0_tokens: log P^0 of every token of the alpha=±1 steered responses under alpha=0 (fp32 log_softmax)."""
    arr = np.asarray(logp0_tokens, dtype=float)
    defect = float(np.mean(arr < -60.0)) if arr.size else float("nan")
    return GateResult("G0.7", arr.size > 0 and defect == 0.0, dict(support_defect=defect, n_tokens=int(arr.size)),
                      criteria="defect = log P^0(y_k) < −60 的 token 比例；纯温度采样下 = 0")


# ---------------------------------------------------------------- GATES.md (§7.0)
def gate_entry(gate: str, title: str, run_id: str, inputs: str, results: Sequence[GateResult], decision: str,
               notes: str = "", date: Optional[str] = None) -> str:
    if decision not in DECISIONS:
        raise ValueError(decision)
    date = date or _dt.date.today().isoformat()
    crit = "; ".join(f"[{r.name}] {r.criteria}" for r in results if r.criteria)
    res = "; ".join(f"[{r.name}] {'PASS' if r.passed else 'FAIL'}: {r.results_text()}" for r in results)
    lines = [f"## {gate} — {title}   run_id={run_id}   date={date}",
             f"Inputs: {inputs}",
             f"Pre-registered criteria: {crit}",
             f"Results: {res}",
             f"Decision: {decision}" + (" (stop and report)" if decision == "GREY" else ""),
             f"Notes: {notes}", ""]
    return "\n".join(lines)


def g0_decision(results: Sequence[GateResult]) -> str:
    """GO only when all eight G0 tests are present and pass; any failure => KILL (plan §0.4: stop and report)."""
    names = {r.name for r in results}
    missing = [t for t in G0_TESTS if t not in names]
    if missing:
        return "GREY"
    return "GO" if all(r.passed for r in results) else "KILL"


def write_gates_md(results: Sequence[GateResult], path: str, run_id: str, inputs: str = "", notes: str = "",
                   gate: str = "G0", title: str = "Serving 忠实性", decision: Optional[str] = None) -> str:
    if decision is None:
        if gate != "G0":
            raise ValueError("decision must be given explicitly for gates other than G0")
        decision = g0_decision(results)
        names = {r.name for r in results}
        missing = [t for t in G0_TESTS if t not in names]
        if missing:
            notes = (notes + " " if notes else "") + f"missing tests: {missing}"
    text = gate_entry(gate, title, run_id, inputs, results, decision, notes)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")
    return decision
