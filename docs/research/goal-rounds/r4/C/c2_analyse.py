"""r4 route C: analysis of the nested Monte Carlo (c1_nested_mc.py outputs).
Theorem 1 constants (sigma_delta for reject / non-PD / width<=w0 with outer-bootstrap CIs and the uniform bound at
P(D) in {0.5, 0.25, 0.1}), the selection-on-configuration constant sigma_0, rule-specific reuse and selection terms
(stage 1: Vhat32>median, PD32, PD-margin-128-hat rules, certify-32 / adopt-128 rules, plug-in adversarial rule), and
stage-2 availability / conditional operating characteristics of rule R128 and of the escalation to 512.
Environment: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 2026-10-19."""
import glob, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c_common import W0, between_variance_component, bootstrap_outer, exact_binom_ci

HERE = os.path.dirname(os.path.abspath(__file__))
SE_NAMES = ("HC1", "CR1")
PIS = (0.5, 0.25, 0.1)


def bvc_with_ci(y, rng, B=2000):
    est = between_variance_component(y)
    boots = bootstrap_outer(lambda yy: between_variance_component(yy), [y], rng, B)
    ucl = float(np.percentile(boots, 95)); lcl = float(np.percentile(boots, 5))
    return dict(estimate=est, ci90_outer_bootstrap=[lcl, ucl], ucl95=ucl, se_boot=float(boots.std()),
                sd_delta_ucl=float(np.sqrt(max(ucl, 0.0))), sd_delta_point=float(np.sqrt(max(est, 0.0))),
                uniform_bound_at_pi={str(p): float(np.sqrt(max(ucl, 0.0)) * np.sqrt((1 - p) / p)) for p in PIS})


def wq(w, qs=(50, 90)):
    return [float(np.percentile(w, q)) for q in qs]


def rule_report(D, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng, B=1000):
    n_out, n_in = rej_r.shape
    pi = float(D.mean()); nf = int(D.sum())
    if nf < 5:
        return dict(P_fired=pi, n_fired=nf, note="too few fired outers")
    ybar = (rej_r.astype(float) - rej_f.astype(float)).mean(1)
    fr, ff = rej_r.mean(1), rej_f.mean(1)
    diff = float(ybar[D].mean()); se_diff = float(ybar[D].std(ddof=1) / np.sqrt(nf))
    sel = float(ff[D].mean() - ff.mean())
    sel_boot = bootstrap_outer(lambda d, f: f[d].mean() - f.mean() if d.sum() > 0 else np.nan, [D, ff], rng, B)
    return dict(P_fired=pi, n_fired=nf,
                size_reuse_given_fire=float(fr[D].mean()), size_fresh_given_fire=float(ff[D].mean()),
                se_size_given_fire=float(fr[D].std(ddof=1) / np.sqrt(nf)),
                reuse_minus_fresh=diff, se=se_diff,
                selection_fresh_minus_uncond=sel, se_selection=float(np.nanstd(sel_boot)),
                nonpd_reuse_given_fire=float(1 - ok_r[D].mean()), nonpd_fresh_given_fire=float(1 - ok_f[D].mean()),
                width_reuse_q50_q90_given_fire=wq(wid_r[D].ravel()), width_fresh_q50_q90_given_fire=wq(wid_f[D].ravel()),
                P_width_le_w0_reuse_given_fire=float((wid_r[D] <= W0).mean()),
                P_width_le_w0_fresh_given_fire=float((wid_f[D] <= W0).mean()))


def analyse_stage1(z, rng):
    out = dict(stage=1, world=str(z["world"]), g=str(z["g"]), seed=int(z["seed"]), n_out=int(z["n_out"]), n_in=int(z["n_in"]),
               clip_rate=float(z["clip_rate"]), cells={})
    pd32, vhat, margin, wmax, w020 = z["pd"], z["vhat"], z["margin"], z["wpred_max"], z["wpred_020"]
    out["pilot_stats"] = dict(P_PD32=float(pd32.mean()), vhat_median=float(np.median(vhat)), margin_median=float(np.median(margin)),
                              P_margin_pos=float((margin > 0).mean()),
                              wpred32_max_q10_50_90=[float(np.nanpercentile(wmax, q)) for q in (10, 50, 90)] if np.isfinite(wmax).any() else None,
                              wpred32_020_q10_50_90=[float(np.nanpercentile(w020, q)) for q in (10, 50, 90)] if np.isfinite(w020).any() else None,
                              P_certify32_max=float((pd32 & (np.nan_to_num(wmax, nan=np.inf) <= W0)).mean()),
                              P_certify32_020=float((pd32 & (np.nan_to_num(w020, nan=np.inf) <= W0)).mean()))
    for s, sname in enumerate(SE_NAMES):
        rej_r, rej_f = z["rej"][0, s], z["rej"][1, s]; ok_r, ok_f = z["ok"][0, s], z["ok"][1, s]; wid_r, wid_f = z["wid"][0, s], z["wid"][1, s]
        cell = dict(unconditional=dict(size_reuse=float(rej_r.mean()), size_fresh=float(rej_f.mean()),
                                       se_size=float(rej_r.mean(1).std(ddof=1) / np.sqrt(rej_r.shape[0])),
                                       nonpd_reuse=float(1 - ok_r.mean()), nonpd_fresh=float(1 - ok_f.mean()),
                                       width_reuse_q50_q90=wq(wid_r.ravel()), width_fresh_q50_q90=wq(wid_f.ravel()),
                                       P_width_le_w0_reuse=float((wid_r <= W0).mean()), P_width_le_w0_fresh=float((wid_f <= W0).mean())))
        cell["theorem1"] = {
            "reject": bvc_with_ci(rej_r.astype(float) - rej_f.astype(float), rng),
            "nonpd": bvc_with_ci(ok_r.astype(float) - ok_f.astype(float), rng),
            "width_le_w0": bvc_with_ci((wid_r <= W0).astype(float) - (wid_f <= W0).astype(float), rng)}
        cell["selection_sigma0_fresh_reject"] = bvc_with_ci(rej_f.astype(float), rng)
        cell["total_sigma_reuse_reject"] = bvc_with_ci(rej_r.astype(float), rng)
        ybar = (rej_r.astype(float) - rej_f.astype(float)).mean(1)
        rules = {"Vhat32>median": vhat > np.median(vhat), "PD32": pd32, "not PD32": ~pd32,
                 "PDmargin128hat>median": margin > np.median(margin), "PDmargin128hat>0": margin > 0,
                 "certify32 (PD32 & wpred_max<=w0)": pd32 & (np.nan_to_num(wmax, nan=np.inf) <= W0),
                 "adopt128 = not certify32": ~(pd32 & (np.nan_to_num(wmax, nan=np.inf) <= W0)),
                 "certify32 plug-in (PD32 & wpred_020<=w0)": pd32 & (np.nan_to_num(w020, nan=np.inf) <= W0),
                 "adopt128 plug-in": ~(pd32 & (np.nan_to_num(w020, nan=np.inf) <= W0)),
                 "adversarial upper-tail of ybar (plug-in, upward-biased)": ybar > np.median(ybar)}
        cell["rules"] = {k: rule_report(D, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng) for k, D in rules.items()}
        out["cells"][sname] = cell
    return out


def analyse_stage2(z, rng):
    out = dict(stage=2, world=str(z["world"]), g=str(z["g"]), seed=int(z["seed"]), n_out=int(z["n_out"]), n_in=int(z["n_in"]),
               clip_rate=float(z["clip_rate"]), cells={})
    pd128, vhat, margin, wmax, w020 = z["pd"], z["vhat"], z["margin"], z["wpred_max"], z["wpred_020"]
    cert_max = pd128 & (np.nan_to_num(wmax, nan=np.inf) <= W0); cert_020 = pd128 & (np.nan_to_num(w020, nan=np.inf) <= W0)
    n_out = pd128.size
    out["availability"] = dict(P_PD128=float(pd128.mean()), ci_PD128=exact_binom_ci(int(pd128.sum()), n_out),
                               P_certify128_max=float(cert_max.mean()), ci_certify128_max=exact_binom_ci(int(cert_max.sum()), n_out),
                               P_certify128_020=float(cert_020.mean()), ci_certify128_020=exact_binom_ci(int(cert_020.sum()), n_out),
                               P_escalate512_max=float(1 - cert_max.mean()), P_escalate512_020=float(1 - cert_020.mean()),
                               wpred128_max_q10_50_90=[float(np.nanpercentile(wmax, q)) for q in (10, 50, 90)] if np.isfinite(wmax).any() else None,
                               wpred128_020_q10_50_90=[float(np.nanpercentile(w020, q)) for q in (10, 50, 90)] if np.isfinite(w020).any() else None,
                               P_margin512hat_pos=float((margin > 0).mean()), vhat128_median=float(np.median(vhat)))
    for s, sname in enumerate(SE_NAMES):
        r128, o128, w128 = z["rej"][0, s], z["ok"][0, s], z["wid"][0, s]
        rej_r, rej_f = z["rej"][1, s], z["rej"][2, s]; ok_r, ok_f = z["ok"][1, s], z["ok"][2, s]; wid_r, wid_f = z["wid"][1, s], z["wid"][2, s]
        def cond128(D):
            nf = int(D.sum())
            if nf < 5:
                return dict(P=float(D.mean()), n_fired=nf, note="too few fired outers")
            return dict(P=float(D.mean()), n_fired=nf, size=float(r128[D].mean()), se_size=float(r128[D].mean(1).std(ddof=1) / np.sqrt(nf)),
                        nonpd=float(1 - o128[D].mean()), width_q50_q90=wq(w128[D].ravel()), P_width_le_w0=float((w128[D] <= W0).mean()))
        cell = dict(test128_unconditional=cond128(np.ones(n_out, bool)),
                    test128_given_certify_max=cond128(cert_max), test128_given_certify_020=cond128(cert_020),
                    test128_given_PD128=cond128(pd128),
                    test512_unconditional=dict(size_reuse=float(rej_r.mean()), size_fresh=float(rej_f.mean()),
                                               se_size=float(rej_r.mean(1).std(ddof=1) / np.sqrt(n_out)),
                                               nonpd_reuse=float(1 - ok_r.mean()), nonpd_fresh=float(1 - ok_f.mean()),
                                               width_reuse_q50_q90=wq(wid_r.ravel()), width_fresh_q50_q90=wq(wid_f.ravel())),
                    theorem1_512stage={"reject": bvc_with_ci(rej_r.astype(float) - rej_f.astype(float), rng),
                                       "nonpd": bvc_with_ci(ok_r.astype(float) - ok_f.astype(float), rng),
                                       "width_le_w0": bvc_with_ci((wid_r <= W0).astype(float) - (wid_f <= W0).astype(float), rng)},
                    rules512={"escalate (not certify128_max)": rule_report(~cert_max, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng),
                              "escalate plug-in (not certify128_020)": rule_report(~cert_020, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng),
                              "not PD128": rule_report(~pd128, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng),
                              "PD128": rule_report(pd128, rej_r, rej_f, ok_r, ok_f, wid_r, wid_f, rng)})
        out["cells"][sname] = cell
    return out


if __name__ == "__main__":
    rng = np.random.default_rng(777)
    results = {}
    for f in sorted(glob.glob(os.path.join(HERE, "c1_stage*_*.npz"))):
        z = np.load(f)
        res = analyse_stage1(z, rng) if int(z["stage"]) == 1 else analyse_stage2(z, rng)
        key = os.path.basename(f)[:-4]
        results[key] = res
        print("====", key, "clip", res["clip_rate"], flush=True)
        if res["stage"] == 1:
            print(" pilot:", json.dumps(res["pilot_stats"]))
            for sname, cell in res["cells"].items():
                print(f" [{sname}] uncond:", json.dumps(cell["unconditional"]))
                for ev, v in cell["theorem1"].items():
                    print(f" [{sname}] Thm1 {ev}: sigma2={v['estimate']:.3e} ci90={v['ci90_outer_bootstrap'][0]:.2e},{v['ci90_outer_bootstrap'][1]:.2e} sd_ucl={v['sd_delta_ucl']:.4f} bound@pi=", v["uniform_bound_at_pi"])
                print(f" [{sname}] sigma0(fresh reject) sd_ucl={cell['selection_sigma0_fresh_reject']['sd_delta_ucl']:.4f}  sigma_tot(reuse reject) sd_ucl={cell['total_sigma_reuse_reject']['sd_delta_ucl']:.4f}")
                for rn, rr in cell["rules"].items():
                    print(f" [{sname}] rule {rn}:", json.dumps(rr))
        else:
            print(" availability:", json.dumps(res["availability"]))
            for sname, cell in res["cells"].items():
                for k in ("test128_unconditional", "test128_given_certify_max", "test128_given_certify_020", "test128_given_PD128", "test512_unconditional"):
                    print(f" [{sname}] {k}:", json.dumps(cell[k]))
                for ev, v in cell["theorem1_512stage"].items():
                    print(f" [{sname}] Thm1@512 {ev}: sigma2={v['estimate']:.3e} ci90={v['ci90_outer_bootstrap'][0]:.2e},{v['ci90_outer_bootstrap'][1]:.2e} sd_ucl={v['sd_delta_ucl']:.4f} bound@pi=", v["uniform_bound_at_pi"])
                for rn, rr in cell["rules512"].items():
                    print(f" [{sname}] rule512 {rn}:", json.dumps(rr))
    json.dump(results, open(os.path.join(HERE, "c2_analysis.json"), "w"), indent=1)
