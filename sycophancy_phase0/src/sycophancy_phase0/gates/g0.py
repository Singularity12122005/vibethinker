"""G0 — serving fidelity (plan §7.1): decision statistics and the GATES.md writer (§7.0).

Model-driven data collection lives in ``gates/g0_runner.py``; this module turns its outputs into GateResults.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..analysis.tost import chi2_homogeneity_p, paired_cluster_bootstrap_diff, tost_pass, tv_distance, tv_upper_bound

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
def g0_1(n_mismatch: int, n_total: int, segment_mismatches: Optional[int] = None) -> GateResult:
    """``segment_mismatches``: §4.1 (v1.4, memo I1) count of turns whose whole-increment encoding differed from the piecewise one
    (reported, not a criterion)."""
    rate = n_mismatch / n_total if n_total else float("nan")
    return GateResult("G0.1", n_total > 0 and rate <= 0.01, dict(mismatch_rate=rate, n=n_total, segment_mismatches=segment_mismatches),
                      criteria="模板一致性：id 拼接与 apply_chat_template 文本路径逐位比较，不一致率 ≤1%；segment_mismatches 只报告")


def g0_2(checks: Dict[str, bool], sampler_chi2_p: float) -> GateResult:
    """checks: the §4.4 self-checks + processor-list check, all must be True; sampler χ² p>0.01 (§4.3)."""
    d: Dict[str, object] = {k: bool(v) for k, v in checks.items()}
    d["sampler_chi2_p"] = float(sampler_chi2_p)
    ok = all(bool(v) for v in checks.values()) and sampler_chi2_p > 0.01
    return GateResult("G0.2", ok, d, criteria="§4.4 四项 hook 自检、processor 列表不含 TemperatureLogitsWarper、首 token χ² p>0.01：全部通过")


# ---------------------------------------------------------------- G0.3
def g0_3(kl_first_token: np.ndarray, n_not_applicable: int = 0, *, min_valid: int = 150, max_na_rate: float = 0.25,
         neg_tol: float = -1e-6) -> GateResult:
    """kl_first_token: per-h_3 KL(cache-reuse || recompute) of the fp32 first-token distribution at T (nats).

    Three kinds of entry are told apart (round 9/10): NaN = the §4.2 "cache 不适用" item — by the contract with
    ``g0_runner.cache_vs_recompute_kl`` NaN is written ONLY by the verified prefix-mismatch path, the runner encodes every
    numerical fault (non-finite logits, non-finite KL) as +inf with a "FAULT" reason (counted, excluded, never a pass;
    ``n_not_applicable`` adds items dropped before the array was built); ±inf or a KL below ``neg_tol`` = a NUMERICAL FAULT
    (a KL cannot be negative beyond rounding; faults fail the gate and G0 KILLs); everything else = a valid measurement
    (tiny negatives within ``neg_tol`` are clamped to 0).  Coverage: ``min_valid`` valid items
    (plan: 150 of the 200 h_3) and a not-applicable rate ≤ ``max_na_rate``, else the gate fails as "coverage" (G0 GREY).
    ``details["kind"]`` ∈ {ok, median_only, q95, coverage, fault} drives ``g0_decision``."""
    kl = np.asarray(kl_first_token, float)
    is_nan = np.isnan(kl)
    is_inf = np.isinf(kl)
    is_neg = (~is_nan) & (~is_inf) & (kl < neg_tol)
    valid = (~is_nan) & (~is_inf) & (~is_neg)
    fin = np.clip(kl[valid], 0.0, None)
    n_faults = int(is_inf.sum() + is_neg.sum())
    n_na = int(n_not_applicable) + int(is_nan.sum())
    n_valid = int(fin.size)
    n_total = n_valid + n_na + n_faults
    med = float(np.median(fin)) if n_valid else float("nan")
    q95 = float(np.quantile(fin, 0.95)) if n_valid else float("nan")
    median_ok, q95_ok = bool(n_valid > 0 and med < 1e-3), bool(n_valid > 0 and q95 < 1e-2)
    na_rate = (n_na / n_total) if n_total else float("nan")
    coverage_ok = bool(n_valid >= int(min_valid) and n_total > 0 and na_rate <= max_na_rate)
    fault_ok = n_faults == 0
    kind = ("fault" if not fault_ok else "coverage" if not coverage_ok else "q95" if not q95_ok else "median_only" if not median_ok else "ok")
    return GateResult("G0.3", median_ok and q95_ok and coverage_ok and fault_ok,
                      dict(delta_floor_median=med, delta_floor_q95=q95, median_ok=median_ok, q95_ok=q95_ok, coverage_ok=coverage_ok,
                           fault_ok=fault_ok, kind=kind, n=n_valid, n_faults=n_faults, n_not_applicable=n_na, not_applicable_rate=na_rate,
                           min_valid=int(min_valid), max_na_rate=float(max_na_rate)),
                      criteria="首 token fp32 log_softmax(logits/T) 的 KL（仅 cache 与 ids_3 前缀逐位一致的有效项）：中位数 <1e-3 nats，95% 分位 <1e-2；"
                               "有效项 ≥150 且不适用比例 ≤25%；±∞ 或负 KL（超出舍入容差）为数值故障；记录为 delta_floor")


# ---------------------------------------------------------------- paired TOST gates
def paired_tost_gate(name: str, e_a: np.ndarray, e_b: np.ndarray, cluster: np.ndarray, margin_pp: float,
                     extra_pass: bool = True, extra: Optional[Dict[str, object]] = None, criteria: str = "") -> GateResult:
    r = paired_cluster_bootstrap_diff(e_a, e_b, cluster, level=0.90)
    ok = tost_pass(r["lo"], r["hi"], margin_pp / 100.0) and extra_pass
    d: Dict[str, object] = dict(diff=r["est"], ci90_lo=r["lo"], ci90_hi=r["hi"], n_clusters=r["n_clusters"], margin=margin_pp / 100.0)
    if extra:
        d.update(extra)
    return GateResult(name, ok, d, criteria=criteria)


def g0_4(e3_same_process: np.ndarray, e3_rebuilt: np.ndarray, h2_cluster: np.ndarray, ids_identical: bool,
         greedy_identical: bool, first_logit_maxdiff: float, text_path_mismatch_rate: float, design_ok: bool = True,
         design_notes: str = "") -> GateResult:
    """Clusters = the 50 h_2 (y_2 nested within h_2; v1.3 — the y_2-level cluster was too fine if the discrepancy is
    h_2-specific).  ``design_ok``/``design_notes`` (v1.4): whether the two phases ran as the §7.1 design note requires
    (phase 1 on the hooked HF engine from in-memory ids_3, phase 2 without the hook, first-token logits measured);
    an unmeasured logit difference (NaN) fails the gate rather than passing silently."""
    extra_ok = bool(ids_identical and greedy_identical and np.isfinite(first_logit_maxdiff) and first_logit_maxdiff < 1e-3
                    and text_path_mismatch_rate <= 0.01 and design_ok)
    return paired_tost_gate("G0.4", e3_same_process, e3_rebuilt, h2_cluster, margin_pp=1.5, extra_pass=extra_ok,
                            extra=dict(ids_identical=ids_identical, greedy_identical=greedy_identical,
                                       first_logit_maxdiff=first_logit_maxdiff, first_logits_measured=bool(np.isfinite(first_logit_maxdiff)),
                                       text_path_mismatch_rate=text_path_mismatch_rate, design_ok=bool(design_ok), design_notes=design_notes),
                            criteria="(i)(ii) ids_3 逐位相同、greedy 续写逐 token 相同、首 token logits max|Δ|<1e-3；(ii)(iii) 不一致率 ≤1%；"
                                     "e_3 率差的配对（按 h_2 聚类）cluster bootstrap 90% CI ⊂ (−1.5, 1.5)pp")


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
def g0_6(u3_arm_idx_a: Sequence[int], u3_arm_idx_b: Sequence[int], deterministic: bool, n_arms: int = 5) -> GateResult:
    """Inputs are per-draw ARM INDICES (0..n_arms-1) of u_3 under two histories (controllers.contract_check).
    Random policies: equivalence via the 95% upper bound TV̂ + 1.645·SE_boot < 0.02 at n >= 50000 draws per
    history (null bound ≈0.01; at n = 20000 the null itself fails ≈8%); χ² p reported only (v1.2's "p>0.01" made
    the written TV tolerance illusory — effective tolerance ≈0.005)."""
    crit = "确定性：u_3 逐位相同；随机：各 n≥50000，5 臂频率 TV 的 95% 上界 TV̂+1.645·SE_boot <0.02（χ² p 仅报告）"
    a = np.asarray(u3_arm_idx_a); b = np.asarray(u3_arm_idx_b)
    for arr in (a, b):
        if arr.size == 0 or not np.issubdtype(arr.dtype, np.integer) or arr.min() < 0 or arr.max() >= n_arms:
            raise ValueError("g0_6 expects integer arm indices in [0, n_arms) per draw, not u values or histograms")
    if deterministic:
        ok = a.shape == b.shape and bool(np.all(a == b))
        return GateResult("G0.6", ok, dict(identical=ok, n=int(a.size)), criteria=crit)
    ca = np.bincount(a, minlength=n_arms)
    cb = np.bincount(b, minlength=n_arms)
    tvr = tv_upper_bound(ca, cb)
    p = chi2_homogeneity_p(ca, cb)
    n = min(int(a.size), int(b.size))
    return GateResult("G0.6", n >= 50000 and tvr["tv_upper"] < 0.02, dict(tv=tvr["tv"], tv_upper95=tvr["tv_upper"], chi2_p=p, n=n), criteria=crit)


# ---------------------------------------------------------------- G0.7
def g0_7(logp0_tokens: np.ndarray) -> GateResult:
    """logp0_tokens: fp32 log P^0 (temperature-0.7 conditional) of every token of the alpha=±1 steered responses.
    v1.4: support defect = tokens with log P^0 = −inf (zero probability); NaN/+inf = numerical fault; both fail.  Finite
    values below −60 are reported as the 'extremely low baseline probability' share and do not fail the test."""
    arr = np.asarray(logp0_tokens, dtype=float)
    n = int(arr.size)
    n_neg_inf = int(np.sum(np.isneginf(arr)))
    n_bad = int(np.sum(np.isnan(arr) | np.isposinf(arr)))
    low = float(np.mean(np.isfinite(arr) & (arr < -60.0))) if n else float("nan")
    return GateResult("G0.7", n > 0 and n_neg_inf == 0 and n_bad == 0,
                      dict(support_defect=(n_neg_inf / n if n else float("nan")), numerical_faults=n_bad, extremely_low_prob_share=low, n_tokens=n),
                      criteria="支持集缺陷 = log P^0(y_k) = −∞ 的 token 比例（须为 0）；NaN/+∞ 为数值故障（须为 0）；有限但 <−60 的比例只报告")


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
    """GO only when all eight G0 tests are present and pass; any failure => KILL (plan §0.4: stop and report).

    Pre-registered amendment before the formal G0 (plan §7.1 G0.3 row, rounds 8–10).  Order: (1) any failure among the other
    seven tests => KILL, never masked by a G0.3 tier; (2) G0.3 numerical fault (±inf / negative KL) => KILL; (3) G0.3 coverage
    insufficient or 95% quantile ≥ 1e-2 => GREY; (4) only the median criterion failed => GO with the appendix cache-reuse regime
    disabled and delta_floor recorded (analyses relying on response log-probs / gradients / KL must first pass the
    generation-vs-teacher-forcing consistency diagnostic, RUNBOOK §6 item 2).  Whether the floor can be reduced (attention
    backend, precision) is an open question, not a premise of this rule."""
    names = {r.name for r in results}
    missing = [t for t in G0_TESTS if t not in names]
    if missing:
        return "GREY"
    by = {r.name: r for r in results}
    if any(not r.passed for r in results if r.name != "G0.3"):
        return "KILL"                                    # every other mandatory failure stops first: G0.3's tiers never mask it
    g03 = by["G0.3"]
    if g03.passed:
        return "GO"
    kind = g03.details.get("kind")
    if kind == "fault":
        return "KILL"                                    # ±inf / negative KL: a measurement-pipeline defect
    if kind in ("coverage", "q95"):
        return "GREY"
    if kind == "median_only" or (g03.details.get("q95_ok", False) and g03.details.get("coverage_ok", True) and g03.details.get("fault_ok", True)):
        return "GO"                                      # cache regime disabled, delta_floor recorded (plan §7.1 G0.3 row)
    return "GREY"


def g0_notes(results: Sequence[GateResult]) -> str:
    """The GATES.md note that the G0.3 amendment requires (empty when G0.3 passed or is missing).  Always consistent with
    ``g0_decision``: when another mandatory test fails, the note states the KILL and reports G0.3's tier as non-deciding."""
    by = {r.name: r for r in results}
    g03 = by.get("G0.3")
    if g03 is None or g03.passed:
        return ""
    med = g03.details.get("delta_floor_median", float("nan"))
    kind = g03.details.get("kind")
    others_failed = [r.name for r in results if r.name != "G0.3" and not r.passed]
    if others_failed:
        return f"KILL：{others_failed} 失败；G0.3 处于 {kind} 档（delta_floor={med:.2e} nats），不改变判定"
    if kind == "fault":
        return f"G0.3 数值故障（±∞ 或负 KL {g03.details.get('n_faults')} 项）：测量管线缺陷，KILL"
    if kind == "coverage":
        return (f"G0.3 覆盖不足（有效 {g03.details.get('n')} 项，不适用比例 {g03.details.get('not_applicable_rate'):.2f}）：GREY，补足样本后重跑")
    if kind == "median_only":
        return (f"G0.3 中位数判据未达（delta_floor={med:.2e} nats）：附录跨轮 cache-reuse regime 禁用，不依赖该 regime 的工作继续；"
                "依赖回答概率/梯度/分布差异的分析须先完成实际计算路径的一致性诊断（RUNBOOK §6 第 2 项）；delta_floor 与 §4.7 的 KL 阈值并列报告")
    return "G0.3 95% 分位 ≥1e-2 nats：数值底噪达 α_max KL 预算的 1/10，GREY（先查注意力后端/精度）"


def write_g0_summary(run_path: str, results: Sequence[GateResult], extra: Optional[dict] = None) -> str:
    """tables/G0_summary.json: every G0 result plus ``delta_floor_median`` (read by stage_g41 for the 10x rule)."""
    import json
    import os

    by = {r.name: r for r in results}
    d = dict(results={r.name: dict(passed=bool(r.passed), details=r.details, criteria=r.criteria) for r in results},
             decision=g0_decision(results), notes=g0_notes(results),
             delta_floor_median=(by["G0.3"].details.get("delta_floor_median") if "G0.3" in by else None), **(extra or {}))
    os.makedirs(os.path.join(run_path, "tables"), exist_ok=True)
    path = os.path.join(run_path, "tables", "G0_summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, default=str)
    return path


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
        extra_note = g0_notes(results)
        if extra_note:
            notes = (notes + " " if notes else "") + extra_note
    text = gate_entry(gate, title, run_id, inputs, results, decision, notes)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")
    return decision
