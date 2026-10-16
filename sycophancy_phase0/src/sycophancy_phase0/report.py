"""REPORT.md and figures (plan §8.10, §10.3): assembled from GATES.md, DEVIATIONS.md and tables/<gate>_summary.json.
Figures use matplotlib when importable (optional dependency); otherwise the data behind each figure is written as CSV.
"""
from __future__ import annotations

import csv
import glob
import json
import os
from typing import Dict, List, Optional


def _load_summaries(run_path: str) -> Dict[str, dict]:
    out = {}
    for p in sorted(glob.glob(os.path.join(run_path, "tables", "*_summary.json"))):
        out[os.path.basename(p)[: -len("_summary.json")]] = json.load(open(p, encoding="utf-8"))
    return out


def write_report(run_path: str, run_id: str, power_table: Optional[dict] = None, recommendation: Optional[str] = None) -> str:
    gates = open(os.path.join(run_path, "GATES.md"), encoding="utf-8").read() if os.path.exists(os.path.join(run_path, "GATES.md")) else ""
    devs = open(os.path.join(run_path, "DEVIATIONS.md"), encoding="utf-8").read() if os.path.exists(os.path.join(run_path, "DEVIATIONS.md")) else ""
    summaries = _load_summaries(run_path)
    lines = [f"# REPORT — run_id={run_id}", "", "## 1. Gate 判据 / 结果 / 决策", "", gates.strip(), "", "## 2. 偏离记录", "", devs.strip(), ""]
    lines += ["## 3. 各 Gate 汇总表（tables/*_summary.json）", ""]
    for g, s in summaries.items():
        dec = s.get("decision", "")
        keys = [k for k in s if k not in ("per_prefix", "tables", "preds", "cells", "levels", "J_per_prefix")]
        lines.append(f"### {g}  decision={dec}")
        for k in keys[:40]:
            v = s[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)[:300]
            lines.append(f"- {k}: {v}")
        lines.append("")
    if power_table:
        lines += ["## 4. 功效表", "", "| 量 | 值 |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in power_table.items()] + [""]
    lines += ["## 5. 对 G7 的建议", "", recommendation or "（待 G5/G6 完成后填写：做 / 不做 / 改为选符号控制器 / 改思考模式）", ""]
    path = os.path.join(run_path, "REPORT.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def _csv(path: str, header: List[str], rows: List[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def figures(run_path: str) -> List[str]:
    """Produce the §8.10 figures that the available summaries support; returns the written paths."""
    summaries = _load_summaries(run_path)
    fig_dir = os.path.join(run_path, "figures")
    os.makedirs(fig_dir, exist_ok=True)
    written = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        plt = None
    # G1: per-turn concession rates per (family × script) + p̂ histogram
    if "G1" in summaries:
        s = summaries["G1"]
        rows = [[k] + [v["P_e"].get(str(t), v["P_e"].get(t)) for t in (2, 3, 4)] for k, v in s["tables_est"].items() if v.get("n", 0)]
        p = os.path.join(fig_dir, "G1_rates.csv"); _csv(p, ["family|script", "P_e2", "P_e3", "P_e4"], rows); written.append(p)
        ph = [(pid, d["sel"], d["est"]) for pid, d in s["p_hat"].items()]
        p = os.path.join(fig_dir, "G1_phat.csv"); _csv(p, ["problem_id", "p_hat_sel", "p_hat_est"], ph); written.append(p)
        if plt is not None and ph:
            fig, ax = plt.subplots(1, 2, figsize=(8, 3))
            ax[0].hist([x[1] for x in ph], bins=20); ax[0].set_title("p̂_A3 (sel)"); ax[1].hist([x[2] for x in ph], bins=20); ax[1].set_title("p̂_A3 (est)")
            p = os.path.join(fig_dir, "G1_phat_hist.png"); fig.tight_layout(); fig.savefig(p); plt.close(fig); written.append(p)
    # G2′-a: A(λ) curve and per-prefix Var(q)
    if "G2a" in summaries:
        s = summaries["G2a"]
        rows = [[lam, A] for lam, A in s["A_of_lambda"].items()]
        p = os.path.join(fig_dir, "G2a_A_of_lambda.csv"); _csv(p, ["lambda_dose", "A"], rows); written.append(p)
        if plt is not None and rows:
            fig, ax = plt.subplots(figsize=(4, 3)); ax.plot([float(r[0]) for r in rows], [r[1] for r in rows], "o-"); ax.set_xlabel("λ_dose"); ax.set_ylabel("Â (errors)")
            p = os.path.join(fig_dir, "G2a_A_of_lambda.png"); fig.tight_layout(); fig.savefig(p); plt.close(fig); written.append(p)
    # G4-2: dose-response per script
    for g, s in summaries.items():
        if g.startswith("G42") and "tables" in s:
            for sc, tab in s["tables"].items():
                rows = [[d, v["rate"], v["logit"], v["n"]] for d, v in sorted(tab.items(), key=lambda kv: float(kv[0]))]
                p = os.path.join(fig_dir, f"{g}_{sc}_dose.csv"); _csv(p, ["d", "CE4_rate", "logit", "n"], rows); written.append(p)
            if plt is not None:
                fig, ax = plt.subplots(figsize=(4, 3))
                for sc, tab in s["tables"].items():
                    ds = sorted(tab, key=float); ax.plot([float(d) for d in ds], [tab[d]["logit"] for d in ds], "o-", label=sc)
                ax.set_xlabel("d = −α/α_max"); ax.set_ylabel("logit P(CE_4)"); ax.legend()
                p = os.path.join(fig_dir, f"{g}_dose.png"); fig.tight_layout(); fig.savefig(p); plt.close(fig); written.append(p)
    # G3: ladder
    if "G3" in summaries:
        rows = [[lv["level"], lv["R2"], lv.get("delta_R2"), lv.get("delta_R2_lb975")] for lv in summaries["G3"]["levels"]]
        p = os.path.join(fig_dir, "G3_ladder.csv"); _csv(p, ["level", "R2", "delta_R2", "lb975"], rows); written.append(p)
    # G5: factorial heatmap data
    for g in ("G5_pilot", "G5_confirm"):
        if g in summaries and "cells" in summaries[g]:
            rows = [[k, v] for k, v in summaries[g]["cells"].items()]
            p = os.path.join(fig_dir, f"{g}_cells.csv"); _csv(p, ["cell", "Y"], rows); written.append(p)
    return written
