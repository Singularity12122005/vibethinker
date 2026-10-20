"""r4 / Route A: summary of a2_two_stage_sim.py raw arrays.  Applies the certificate thresholds (user decisions: d_0, w_0,
kappa_0) and the tolerance (|size - 0.05| <= 0.02, non-PD <= 2%, q90 width <= 0.15) and reports, per world x g:
  (1) unconditional production results per call (size counts ok=False as non-rejection; width = inf when not ok) and the ratio of
      the simulated median / q90 width to the first-order width w_1 of a1_exact_check.json;
  (2) availability of the 32-stage certificate (pilot = K32) for targets 32 and 128, three response classes, and its conditional
      validity (size / width at the target under REUSE and FRESH regressor counts) -- with exact Clopper-Pearson intervals for
      zero counts;  (3) the same for the 128-stage certificate (pilot = K128, targets 128 (self) and 512);
  (4) Jensen direction of the plug-in D_hat;  (5) sensitivity to (d_0, w_0, kappa_0).
Environment: CPU, python 3.13.16 x86_64, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy import stats
from route_a_lib import beta_moments, overlap_D, Z_ONE_SIDED_95

HERE = os.path.dirname(os.path.abspath(__file__))
A1 = json.load(open(os.path.join(HERE, "a1_exact_check.json")))["first_order_table"]
TOL = dict(size=0.02, non_pd=0.02, w90=0.15)
D0, W0, K0 = 0.05, 0.15, None
Z = Z_ONE_SIDED_95


def cp_interval(k, n, conf=0.95):
    lo = 0.0 if k == 0 else stats.beta.ppf((1 - conf) / 2, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(1 - (1 - conf) / 2, k + 1, n - k)
    return [float(lo), float(hi)]


def q(arr, p):
    return float(np.quantile(arr, p, method="lower"))


def prod_summary(P, idx):
    ok = P[idx, :, 0] == 1
    rej = ok & (np.abs(np.nan_to_num(P[idx, :, 1], nan=0.0)) > 1.96)
    width = np.where(ok, 2 * 1.96 * P[idx, :, 2], np.inf)
    n = ok.size
    return dict(n=int(n), non_pd=float(1 - ok.mean()), non_pd_ci=cp_interval(int((~ok).sum()), n),
                size=float(rej.mean()), size_ci=cp_interval(int(rej.sum()), n), size_given_ok=float(rej[ok].mean()) if ok.any() else None,
                width_q10_50_90=[q(width, 0.1), q(width, 0.5), q(width, 0.9)],
                width_q90_given_ok=q(width[ok], 0.9) if ok.any() else None, width_q50_given_ok=q(width[ok], 0.5) if ok.any() else None)


def passes(s):
    return bool(abs(s["size"] - 0.05) <= TOL["size"] and s["non_pd"] <= TOL["non_pd"] and s["width_q10_50_90"][2] <= TOL["w90"])


def fire_mask(C, names, target, cls, d0=D0, w0=W0, k0=K0):
    nm = list(names); k = len(nm)
    pt, sd = C[:, :k], C[:, k:]
    iD = nm.index("D"); iw = nm.index("w1sup_m%d_c%s" % (target, cls) if cls != "g" else "w1_g_m%d" % target); ik = nm.index("kappa_m%d" % target)
    lcbD = pt[:, iD] - Z * sd[:, iD]; ucbw = pt[:, iw] + Z * sd[:, iw]; lcbk = pt[:, ik] - Z * sd[:, ik]
    f = np.isfinite(lcbD) & np.isfinite(ucbw) & (lcbD >= d0) & (ucbw <= w0)
    if k0 is not None:
        f &= np.isfinite(lcbk) & (lcbk >= k0)
    return f


def main():
    out = {}
    for f in sorted(glob.glob(os.path.join(HERE, "a2_raw_*.npz"))):
        Zf = np.load(f, allow_pickle=True)
        wn, gn = str(Zf["world"]), str(Zf["g"]); P = Zf["prod"]; C32, C128 = Zf["cert32"], Zf["cert128"]
        pn = list(Zf["prod_names"]); n32 = list(Zf["cert32_names"]); n128 = list(Zf["cert128_names"])
        P = np.transpose(P, (1, 0, 2))           # [call, rep, 4]
        reps = P.shape[1]
        types = Zf["types"]; mu0, mu1 = beta_moments(*types[0]), beta_moments(*types[1]); Dtrue = float(overlap_D(mu0, mu1, 0.5)[0])
        cell = dict(world=wn, g=gn, reps=int(reps), seed=int(Zf["seed"]), clip_rate=float(Zf["clip"].mean()), D_true=Dtrue, unconditional={}, world_passes={})
        for i, name in enumerate(pn):
            s = prod_summary(P, i)
            m = int(name.split("_")[0][1:])
            key = "m=%d|g=%s" % (m, gn)
            w1 = A1[wn][key]["width1"]; w1o = A1[wn][key]["width_oracle"]
            s.update(first_order_width1=w1, first_order_oracle=w1o,
                     ratio_median_given_ok_to_w1=(s["width_q50_given_ok"] / w1) if s["width_q50_given_ok"] else None,
                     ratio_q90_to_w1=(s["width_q10_50_90"][2] / w1) if np.isfinite(s["width_q10_50_90"][2]) else None)
            cell["unconditional"][name] = s
            cell["world_passes"][name] = passes(s)
        # Jensen direction of the plug-in D_hat (point estimates stored first in cert arrays)
        D32, D128 = C32[:, n32.index("D")], C128[:, n128.index("D")]
        cell["jensen_Dhat"] = dict(mean_Dhat_32=float(np.nanmean(D32)), mean_Dhat_128=float(np.nanmean(D128)), D_true=Dtrue,
                                   P_Dhat32_le_true=float(np.nanmean(D32 <= Dtrue)), P_Dhat128_le_true=float(np.nanmean(D128 <= Dtrue)),
                                   sd_Dhat_32=float(np.nanstd(D32)), sd_Dhat_128=float(np.nanstd(D128)),
                                   median_delta_sd_D_32=float(np.nanmedian(C32[:, len(n32) + n32.index("D")])),
                                   median_delta_sd_D_128=float(np.nanmedian(C128[:, len(n128) + n128.index("D")])))
        # certificates
        cert = {}
        for stage, C, names, targets in (("stage32", C32, n32, (32, 128)), ("stage128", C128, n128, (128, 512))):
            for target in targets:
                calls = [i for i, nm in enumerate(pn) if nm.startswith("m%d_" % target)]
                for cls in ("inf", "2.0", "g"):
                    fm = fire_mask(C, names, target, cls)
                    entry = dict(availability=float(fm.mean()), availability_ci=cp_interval(int(fm.sum()), reps), n_fired=int(fm.sum()), conditional={})
                    for i in calls:
                        if fm.any():
                            entry["conditional"][pn[i]] = prod_summary(P[:, fm, :], i)
                    # false fire: fires although the world fails the tolerance at the target (HC1 unconditional)
                    hc1 = "m%d_reuse_HC1" % target if target != 32 else "m32_HC1"
                    entry["world_passes_at_target_HC1"] = cell["world_passes"][hc1]
                    entry["P_fire_and_world_fails"] = float(fm.mean()) if not cell["world_passes"][hc1] else 0.0
                    cert["%s|target%d|class_%s" % (stage, target, cls)] = entry
        cell["certificates"] = cert
        # sensitivity grid (stage 32 -> target 128, and stage 32 -> target 32), class 2.0 and g
        sens = {}
        for stage, C, names, target in (("stage32", C32, n32, 128), ("stage32", C32, n32, 32), ("stage128", C128, n128, 128), ("stage128", C128, n128, 512)):
            for cls in ("2.0", "g", "inf"):
                for d0 in (0.02, 0.05, 0.10):
                    for w0 in (0.12, 0.15, 0.20):
                        for k0 in (None, 0.2, 0.5):
                            fm = fire_mask(C, names, target, cls, d0, w0, k0)
                            sens["%s|target%d|class_%s|d0=%.2f|w0=%.2f|k0=%s" % (stage, target, cls, d0, w0, k0)] = float(fm.mean())
        cell["sensitivity_availability"] = sens
        # two-stage (C): reuse vs fresh among fired, main variant stage32 -> 128, class 2.0 and g
        two = {}
        for cls in ("2.0", "g", "inf"):
            fm = fire_mask(C32, n32, 128, cls)
            if fm.sum() >= 20:
                ru = prod_summary(P[:, fm, :], pn.index("m128_reuse_HC1")); fr = prod_summary(P[:, fm, :], pn.index("m128_fresh_HC1"))
                two["class_%s" % cls] = dict(n_fired=int(fm.sum()), size_reuse=ru["size"], size_fresh=fr["size"],
                                             diff=ru["size"] - fr["size"], se_diff_indep_approx=float(np.sqrt((ru["size"] * (1 - ru["size"]) + fr["size"] * (1 - fr["size"])) / fm.sum())),
                                             non_pd_reuse=ru["non_pd"], non_pd_fresh=fr["non_pd"], w90_reuse=ru["width_q10_50_90"][2], w90_fresh=fr["width_q10_50_90"][2])
        cell["two_stage_reuse_vs_fresh"] = two
        out["%s|%s" % (wn, gn)] = cell
        # console
        print("=" * 100); print("%s | g=%s | reps %d | clip %.4f | D_true %.4f" % (wn, gn, reps, cell["clip_rate"], Dtrue))
        for name, s in cell["unconditional"].items():
            print("  %-16s nonPD %.4f size %.4f (ok: %.4f) width q50|ok %.4f q90 %s | w1 %.4f (ratio q50/w1 %.3f) oracle %.4f | pass=%s"
                  % (name, s["non_pd"], s["size"], np.nan if s["size_given_ok"] is None else s["size_given_ok"], np.nan if s["width_q50_given_ok"] is None else s["width_q50_given_ok"], "%.4f" % s["width_q10_50_90"][2],
                     s["first_order_width1"], np.nan if s["ratio_median_given_ok_to_w1"] is None else s["ratio_median_given_ok_to_w1"], s["first_order_oracle"], cell["world_passes"][name]))
        print("  Jensen: mean D_hat(32) %.4f, D_hat(128) %.4f vs D %.4f; P(D_hat32<=D) %.3f; delta-sd(D) median %.4f / %.4f"
              % (cell["jensen_Dhat"]["mean_Dhat_32"], cell["jensen_Dhat"]["mean_Dhat_128"], Dtrue, cell["jensen_Dhat"]["P_Dhat32_le_true"],
                 cell["jensen_Dhat"]["median_delta_sd_D_32"], cell["jensen_Dhat"]["median_delta_sd_D_128"]))
        for k, e in cert.items():
            cond = ""
            for cn, s in e["conditional"].items():
                cond += " | %s: nonPD %.4f size %.4f w90 %.4f" % (cn, s["non_pd"], s["size"], s["width_q10_50_90"][2])
            print("  %-34s avail %.4f [%.4f,%.4f] n=%d passes@target=%s%s" % (k, e["availability"], *e["availability_ci"], e["n_fired"], e["world_passes_at_target_HC1"], cond))
        for k, e in two.items():
            print("  two-stage %s: n_fired %d size reuse %.4f fresh %.4f diff %+.4f (se~%.4f)" % (k, e["n_fired"], e["size_reuse"], e["size_fresh"], e["diff"], e["se_diff_indep_approx"]))
    json.dump(out, open(os.path.join(HERE, "a2_summary.json"), "w"), indent=1)
    print("wrote a2_summary.json")


if __name__ == "__main__":
    main()
