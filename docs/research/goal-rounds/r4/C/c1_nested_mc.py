"""r4 route C, nested Monte Carlo for the two-stage (internal-pilot) procedure with REUSE vs FRESH final counts.

Stage 1 (--stage 1): outer unit o = the 200 pilot counts K32 ~ BetaBin(32, a_t, b_t) (exactly the law of the §7.2b/§7.11 sel
  counts in a Beta world); inner replicate: r | K32 ~ Beta posterior (exact), eta (two 16-draw arms), K96 ~ Bin(96, r),
  K'128 ~ Bin(128, r) independent.  Tests: production degree-2 corrected score at m = 128 with REUSE (K32 + K96) and FRESH (K'128),
  HC1 and CR1 (50 questions x 4 prefixes, 2 per type), common random numbers (same r, eta).  Null b_type = 0.
Stage 2 (--stage 2): outer = K128 ~ BetaBin(128, .); inner: r | K128, eta, K384, K'512; tests at m = 128 on K128 itself (the
  certify-128 branch) and at m = 512 with reuse (K128 + K384) vs fresh (K'512) (the escalate branch).
Outputs: per cell an .npz with inner outcome arrays (reject, ok, width) and the outer counts + pilot statistics, analysed by
c2_analyse.py.  Environment: CPU x86_64, python 3.13.16, numpy 2.5.4, scipy 1.18.1, 4 cores, 2026-10-19."""
import argparse, json, os, sys, time, warnings
import numpy as np
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c_common import (WORLDS, G_CLASS, CLUSTER, W0, SIG2_ETA_MAX, draw_outer_counts, draw_r_posterior, draw_dhat, run_test,
                      pd_flag, vhat_pooled, pd_margin_hat, width_predictor)

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = {1: dict(m_pilot=32, m_extra=96, m_final=128), 2: dict(m_pilot=128, m_extra=384, m_final=512)}
CELLS = {1: [("narrow", "lin"), ("narrow", "quad"), ("narrow", "cheb"), ("halfvar", "lin"), ("wide", "lin")],
         2: [("narrow", "lin"), ("halfvar", "lin"), ("wide", "lin")]}
SEEDS = {1: 4101, 2: 4102}


def run_cell(args):
    stage, world, gname, n_out, n_in = args
    st = STAGES[stage]; m0, m1, m2 = st["m_pilot"], st["m_extra"], st["m_final"]
    types, g = WORLDS[world], G_CLASS[gname]
    seed = SEEDS[stage] * 1000 + sum(map(ord, world + gname))
    rng = np.random.default_rng(seed)
    warnings.simplefilter("ignore")
    # tests: stage 1 -> [final reuse, final fresh]; stage 2 -> [pilot-stage test on K128 itself, final reuse, final fresh]
    n_tests = 2 if stage == 1 else 3
    rej = np.zeros((n_tests, 2, n_out, n_in), bool); ok = np.zeros_like(rej); wid = np.full(rej.shape, np.inf, np.float32)
    Kout = np.zeros((n_out, 200), np.int16)
    pilot = dict(pd=np.zeros(n_out, bool), vhat=np.zeros(n_out), margin=np.zeros(n_out),
                 wpred_max=np.zeros(n_out), wpred_020=np.zeros(n_out))
    clip = 0.0
    t0 = time.time()
    for o in range(n_out):
        K0 = draw_outer_counts(rng, types, m0)
        Kout[o] = K0
        pilot["pd"][o] = pd_flag(K0, m0); pilot["vhat"][o] = vhat_pooled(K0, m0)
        pilot["margin"][o] = pd_margin_hat(K0, m0, m2)
        pilot["wpred_max"][o] = width_predictor(K0, m0, SIG2_ETA_MAX); pilot["wpred_020"][o] = width_predictor(K0, m0, 0.02)
        for l in range(n_in):
            r = draw_r_posterior(rng, types, K0, m0)
            dhat, c = draw_dhat(rng, r, g); clip += c
            Kr = K0 + rng.binomial(m1, r); Kf = rng.binomial(m2, r)
            tests = ([(Kr, m2), (Kf, m2)] if stage == 1 else [(K0, m0), (Kr, m2), (Kf, m2)])
            for v, (K, m) in enumerate(tests):
                for s, cl in enumerate((None, CLUSTER)):
                    ok[v, s, o, l], rej[v, s, o, l], wid[v, s, o, l] = run_test(dhat, K, m, cl)
        if o % 100 == 0:
            print(f"stage{stage} {world}|{gname} outer {o}/{n_out} elapsed {time.time() - t0:.0f}s", flush=True)
    out = os.path.join(HERE, f"c1_stage{stage}_{world}_{gname}.npz")
    np.savez_compressed(out, rej=rej, ok=ok, wid=wid, Kout=Kout, clip_rate=clip / (n_out * n_in), seed=seed,
                        n_out=n_out, n_in=n_in, stage=stage, world=world, g=gname, **pilot)
    return out, time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--stage", type=int, default=1); ap.add_argument("--n_out", type=int, default=1000)
    ap.add_argument("--n_in", type=int, default=200); ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    jobs = [(a.stage, w, g, a.n_out, a.n_in) for (w, g) in CELLS[a.stage]]
    with Pool(a.procs) as pool:
        for out, el in pool.imap_unordered(run_cell, jobs):
            print("done", out, f"{el:.0f}s", flush=True)
