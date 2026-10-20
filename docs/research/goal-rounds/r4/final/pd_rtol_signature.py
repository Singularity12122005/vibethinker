import inspect, re, subprocess, sys
root = sys.argv[1]
sys.path.insert(0, root + "/sycophancy_phase0/src")
from sycophancy_phase0.analysis import g6_iv
head = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
diff = subprocess.run(["git", "-C", root, "diff", "--quiet", "HEAD", "--", "sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py"]).returncode
print("# 修复 3 of detailed-record.md (2026-10-20; the second repair after the v5 gate check): import-time PD tolerance and the signatures of corrected_moment_matrix / endpoint_contrast_poly_cs")
print(f"# worktree HEAD {head}; g6_iv.py diff vs HEAD: {'none' if diff == 0 else 'PRESENT'}")
print("# command: /tmp/claude-0/venv/bin/python -I docs/research/goal-rounds/r4/final/pd_rtol_signature.py <worktree> (sycophancy_phase0/src on sys.path)")
print(f"PD_RTOL = {g6_iv.PD_RTOL!r}")
print("corrected_moment_matrix", inspect.signature(g6_iv.corrected_moment_matrix))
sig = inspect.signature(g6_iv.endpoint_contrast_poly_cs)
print("endpoint_contrast_poly_cs", sig)
print("endpoint_contrast_poly_cs accepts pd_rtol:", "pd_rtol" in sig.parameters)
src = inspect.getsource(g6_iv.endpoint_contrast_poly_cs)
print("internal call:", [l.strip() for l in src.splitlines() if re.search(r"corrected_moment_matrix\(", l)])
