"""Re-review (scope lens) of narrowed r4 C1: does sigma_delta(REJECT) transfer to G6 conditions outside the four cells?
Cells: (A) narrow cheb + question effect v_q ~ N(0, 0.10^2) in the Delta mean beyond r (shared by the 4 prefixes of a question,
both types, so b_type = 0 still holds; violates A0's 'independent across prefixes given r');
(B) narrow lin + same v_q;  (C) wide Beta(2,8)/(2.5,7.5) lin, v_q = 0 (the stage-1 wide cell never reported);
(D) narrow cheb with 32-draw arms (Delta over all 32 per arm), v_q = 0.
Production endpoint_contrast_poly_cs(degree 2) at m = 128, reuse K32+K96 vs fresh K'128, common r, eta. HC1 and CR1."""
import sys, os, time, warnings
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/docs/research/goal-rounds/r4/C")
import numpy as np
from multiprocessing import Pool
from c_common import (WORLDS, G_CLASS, CLUSTER, draw_outer_counts, draw_r_posterior, run_test, pd_flag, vhat_pooled)

HERE = os.path.dirname(os.path.abspath(__file__))


def dhat_draw(rng, r, g, vq, n_arm):
    c0, b1, b2 = g
    delta = c0 + b1 * r + b2 * r ** 2 + vq[CLUSTER]
    qp, qm = np.clip(r + delta / 2, 0, 1), np.clip(r - delta / 2, 0, 1)
    return rng.binomial(n_arm, qp) / n_arm - rng.binomial(n_arm, qm) / n_arm


def run(args):
    name, world, gname, sv, n_arm, n_out, n_in, seed = args
    warnings.simplefilter("ignore")
    rng = np.random.default_rng(seed)
    types, g = WORLDS[world], G_CLASS[gname]
    y = np.zeros((2, n_out, n_in), np.int8); rr = np.zeros((2, n_out, n_in), bool)
    pd32 = np.zeros(n_out, bool); vh = np.zeros(n_out)
    t0 = time.time()
    for o in range(n_out):
        K0 = draw_outer_counts(rng, types, 32)
        pd32[o] = pd_flag(K0, 32); vh[o] = vhat_pooled(K0, 32)
        for l in range(n_in):
            r = draw_r_posterior(rng, types, K0, 32)
            vq = rng.normal(0, sv, 50) if sv > 0 else np.zeros(50)
            d = dhat_draw(rng, r, g, vq, n_arm)
            Kr = K0 + rng.binomial(96, r); Kf = rng.binomial(128, r)
            for s, cl in enumerate((None, CLUSTER)):
                _, a, _ = run_test(d, Kr, 128, cl); _, b, _ = run_test(d, Kf, 128, cl)
                y[s, o, l] = int(a) - int(b); rr[s, o, l] = a
        if o % 100 == 0:
            print(name, o, f"{time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(os.path.join(HERE, f"q1_{name}.npz"), y=y, rr=rr, pd32=pd32, vh=vh)
    return name


if __name__ == "__main__":
    n_out, n_in = int(sys.argv[1]), int(sys.argv[2])
    jobs = [("A_narrow_cheb_vq10", "narrow", "cheb", 0.10, 16, n_out, n_in, 77001),
            ("B_narrow_lin_vq10", "narrow", "lin", 0.10, 16, n_out, n_in, 77002),
            ("C_wide_lin", "wide", "lin", 0.0, 16, n_out, n_in, 77003),
            ("D_narrow_cheb_arm32", "narrow", "cheb", 0.0, 32, n_out, n_in, 77004)]
    with Pool(4) as p:
        for nm in p.imap_unordered(run, jobs):
            print("done", nm, flush=True)
