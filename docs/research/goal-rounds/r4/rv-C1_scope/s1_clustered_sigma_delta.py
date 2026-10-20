"""Scope review of r4 C1: does sigma_delta (reuse effect constant) transfer to question-clustered risks with a non-Beta law?
World: 50 questions x 4 prefixes (2 per type, same CLUSTER layout as route C), logit r = mu_t + u_q + e_i,
u_q ~ N(0, su^2), e_i ~ N(0, se^2), total logit sd 0.24 (~ narrow Beta within-type sd), mu = logit(0.20), logit(0.25).
Inner law r | K32 sampled exactly-in-the-limit by per-question importance resampling from the prior (4 prefixes jointly).
Outcome: g lin = 0.18 - 0.8 r, two 16-draw arms, null b_type = 0, no question effect in Delta beyond r.
Production test endpoint_contrast_poly_cs(degree 2) at m = 128, reuse (K32 + K96) vs fresh K'128, common r and eta. HC1 and CR1."""
import sys, os, time, json
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/C__Sequential_internal-pilot_design__32___128___re-assess__and_validity_under_reuse")
import numpy as np
from multiprocessing import Pool
import warnings
from c_common import draw_dhat, run_test, CLUSTER, TYPES_VEC, G_CLASS, between_variance_component, pd_flag
from scipy.special import expit, logit

MU = np.where(TYPES_VEC == 0, logit(0.20), logit(0.25))
NQ = 50
# prefix index -> question: CLUSTER (type0 prefixes 0..99 -> q 0..49 twice; type1 100..199 -> same)
def prior_draw(rng, su, se, size):
    u = rng.normal(0, su, (size, NQ))
    e = rng.normal(0, se, (size, 200))
    return expit(MU[None, :] + u[:, CLUSTER] + e)

def run(args):
    name, su, se, n_out, n_in, seed = args
    warnings.simplefilter("ignore")
    rng = np.random.default_rng(seed)
    g = G_CLASS["lin"]
    NP = 20000
    y = np.zeros((2, n_out, n_in)); rej_r = np.zeros((2, n_out, n_in), bool)
    pd32 = np.zeros(n_out, bool); ess_min = np.zeros(n_out)
    t0 = time.time()
    for o in range(n_out):
        r0 = prior_draw(rng, su, se, 1)[0]
        K0 = rng.binomial(32, r0)
        pd32[o] = pd_flag(K0, 32)
        # importance resampling per question: prior draws of (u_q, e_i) for all questions at once
        R = prior_draw(rng, su, se, NP)                       # NP x 200
        ll = K0[None, :] * np.log(R) + (32 - K0)[None, :] * np.log1p(-R)
        llq = np.zeros((NP, NQ))
        np.add.at(llq.T, CLUSTER, ll.T)                       # sum log-lik over the 4 prefixes of each question
        w = np.exp(llq - llq.max(0)); w /= w.sum(0)
        ess_min[o] = float((1 / (w ** 2).sum(0)).min())
        idx = np.stack([rng.choice(NP, n_in, p=w[:, q]) for q in range(NQ)], 1)   # n_in x NQ
        for l in range(n_in):
            r = R[idx[l][CLUSTER], np.arange(200)]
            dhat, _ = draw_dhat(rng, r, g)
            Kr = K0 + rng.binomial(96, r); Kf = rng.binomial(128, r)
            for s, cl in enumerate((None, CLUSTER)):
                _, a, _ = run_test(dhat, Kr, 128, cl); _, b, _ = run_test(dhat, Kf, 128, cl)
                y[s, o, l] = float(a) - float(b); rej_r[s, o, l] = a
        if o % 100 == 0:
            print(name, o, f"{time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"s1_{name}.npz"), y=y, rej_r=rej_r, pd32=pd32, ess_min=ess_min)
    return name

if __name__ == "__main__":
    n_out, n_in = int(sys.argv[1]), int(sys.argv[2])
    sd = 0.24
    jobs = [("iid", 0.0, sd, n_out, n_in, 9101), ("clu70", sd * np.sqrt(0.7), sd * np.sqrt(0.3), n_out, n_in, 9102),
            ("clu90", sd * np.sqrt(0.9), sd * np.sqrt(0.1), n_out, n_in, 9103)]
    with Pool(3) as p:
        for nm in p.imap_unordered(run, jobs):
            print("done", nm, flush=True)
