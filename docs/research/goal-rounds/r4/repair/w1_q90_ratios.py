"""Repair-stage arithmetic: realised q90 / first-order width W_1 for every degree-2 cell with a known W_1.
W_1 for the archive lin g (0.18-0.8r, 16-draw arms) from A/a1_exact_check.json first_order_table (C.1 table);
s2/s3/s4 print their own W_1.  check1/check1b width quantiles are over ok replicates only."""
import json, re, sys
R4 = sys.argv[1]
W1 = {("narrow", 32): 0.1444, ("narrow", 128): 0.1071, ("narrow", 512): 0.0982,
      ("halfvar", 128): 0.1428, ("halfvar", 512): 0.1168,
      ("wide", 32): 0.0860, ("wide", 128): 0.0809, ("wide", 512): 0.0796}
rows = []
for line in open(f"{R4}/problem/check1_size_width.out"):
    if "|g=linear|" in line and "|deg=2|" in line:
        key, js = line.split(" ", 1); d = json.loads(js); w, g, m, deg, se = key.split("|")
        m = int(m[2:]); q90 = d["width_q10_50_90"][2]
        rows.append(("check1", f"{w} m={m} {se}", d["non_pd"], q90, W1[(w, m)]))
for line in open(f"{R4}/problem/check1b_compatible_edge.out"):
    key, js = line.split(" ", 1); d = json.loads(js); w = key.split("|")[0]; m = int(key.split("|")[1][2:])
    wk = "narrow" if w.startswith("narrow") else "halfvar" if w.startswith("half") else None
    if wk and (wk, m) in W1:
        rows.append(("check1b", f"{wk} m={m}", d["non_pd"], d["width_q10_50_90"][2], W1[(wk, m)]))
for line in open(f"{R4}/review_A-C1_scope/s2_n200_production.out"):
    mm = re.search(r"^(.*?)\s+w1=([\d.]+) clip=([\d.]+) nonPD=([\d.]+) \| HC1 .*?q90=([\d.]+).*?\| CR1 .*?q90=([\d.]+)", line)
    if mm:
        lab, w1, _, npd, qh, qc = mm.groups()
        rows.append(("s2", lab.strip() + " HC1", float(npd), float(qh), float(w1)))
        rows.append(("s2", lab.strip() + " CR1", float(npd), float(qc), float(w1)))
for line in open(f"{R4}/review_A-C1_scope/s3_c2_eta_end_and_m64.out"):
    mm = re.search(r"^(\w+)\s+(.*?)\s+m=\s*(\d+) w1=([\d.]+) nonPD=([\d.]+) q50=([\d.]+) q90=([\d.na]+)", line)
    if mm:
        w, lab, m, w1, npd, _, q90 = mm.groups()
        rows.append(("s3", f"{w} {lab} m={m}", float(npd), float(q90), float(w1)))
for line in open(f"{R4}/review_A-C1_scope/s4_narm32.out"):
    mm = re.search(r"^(n_arm=\d+ g=\(.*?\))\s+w1=([\d.]+) oracle=[\d.]+\s+q50=[\d.]+ q90=([\d.]+)", line)
    if mm:
        lab, w1, q90 = mm.groups()
        rows.append(("s4", lab, float("nan"), float(q90), float(w1)))
lo = []
for src, lab, npd, q90, w1 in rows:
    r = q90 / w1
    print(f"{src:7s} {lab:62s} nonPD={npd:.4f} q90={q90:.4f} W1={w1:.4f} ratio={r:.3f}")
    if not (npd >= 0.01) and r == r:
        lo.append(r)
print(f"cells with nonPD<1% (or not reported) and finite q90: n={len(lo)} min={min(lo):.3f} max={max(lo):.3f}")
print("all finite ratios > 1:", all((q / w) > 1 for _, _, _, q, w in rows if q == q))
