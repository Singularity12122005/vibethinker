import json
import os

from sycophancy_phase0.report import figures, write_report
from sycophancy_phase0.run import DEFAULT_CONFIG, init_run, record_deviation, write_summary


def test_report_and_figures(tmp_path):
    d = init_run(str(tmp_path), "RPT", DEFAULT_CONFIG)
    write_summary(d, "G1", dict(decision="GO", tables_est={"F2|A3": dict(n=10, P_e={"2": 0.1, "3": 0.2, "4": 0.3})}, p_hat={"p1": dict(sel=0.3, est=0.35)}))
    write_summary(d, "G2a", dict(decision="GO-with-caveat", A_of_lambda={"0.05": 0.001, "0.1": 0.002}, J=0.03))
    write_summary(d, "G42_v_cap_perp", dict(decision="GO", tables={"A3": {"-1.0": dict(rate=0.5, logit=0.0, n=10), "1.0": dict(rate=0.7, logit=0.85, n=10)}}))
    record_deviation(d, "x", "y", "z")
    with open(os.path.join(d, "GATES.md"), "a", encoding="utf-8") as f:
        f.write("## G1 — 校准 pilot   run_id=RPT   date=2026-10-16\nInputs: i\nPre-registered criteria: c\nResults: r\nDecision: GO\nNotes:\n")
    p = write_report(d, "RPT", power_table={"F_80": 105}, recommendation="做")
    txt = open(p, encoding="utf-8").read()
    assert "## G1 — 校准 pilot" in txt and "偏离：x" in txt and "| F_80 | 105 |" in txt and "### G2a  decision=GO-with-caveat" in txt and txt.endswith("做\n")
    written = figures(d)
    names = {os.path.basename(w) for w in written}
    assert {"G1_rates.csv", "G1_phat.csv", "G2a_A_of_lambda.csv", "G42_v_cap_perp_A3_dose.csv"} <= names
    rows = open(os.path.join(d, "figures", "G42_v_cap_perp_A3_dose.csv"), encoding="utf-8").read().splitlines()
    assert rows[0] == "d,CE4_rate,logit,n" and rows[1].startswith("-1.0,0.5")
