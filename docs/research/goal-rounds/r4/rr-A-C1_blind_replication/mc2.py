import sys
from fractions import Fraction as Fr
import numpy as np
sys.path.insert(0, '/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_A-C1_blind_replication')
sys.path.insert(0, '/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src')
import cf
from sycophancy_phase0.analysis.g6_iv import endpoint_contrast_poly_cs

W = {'narrow': ((20, 80), (25, 75)), 'half': ((40.5, 162), (50.6, 151.8)), 'wide': ((2, 8), (2.5, 7.5))}
WF = {'narrow': ((20, 80), (25, 75)), 'half': ((Fr(81, 2), 162), (Fr(253, 5), Fr(759, 5))), 'wide': ((2, 8), (Fr(5, 2), Fr(15, 2)))}
w = {0: Fr(1, 2), 1: Fr(1, 2)}
beta = (Fr(18, 100), Fr(-8, 10), Fr(0))
clip = sys.argv[1] == 'clip'
n = int(sys.argv[2]); reps = int(sys.argv[3])
rng = np.random.default_rng(int(sys.argv[4]))
for name in sys.argv[5].split(','):
    moms = {0: cf.beta_moms(*WF[name][0]), 1: cf.beta_moms(*WF[name][1])}
    for m in [int(x) for x in sys.argv[6].split(',')]:
        v, D, _, _ = cf.var1_total(moms, w, m, beta, cf.sig2_arms(beta))
        sdf = float(v) ** 0.5
        ests, ses, clips, fails = [], [], [], 0
        for rep in range(reps):
            t = np.r_[np.zeros(n // 2), np.ones(n // 2)].astype(int)
            r = np.where(t == 0, rng.beta(*W[name][0], n), rng.beta(*W[name][1], n))
            g = 0.18 - 0.8 * r
            qp, qm = r + g / 2, r - g / 2
            if clip:
                clips.append(np.mean((qp < 0) | (qp > 1) | (qm < 0) | (qm > 1)))
                qp, qm = np.clip(qp, 0, 1), np.clip(qm, 0, 1)
            else:
                ok = (qp >= 0) & (qp <= 1) & (qm >= 0) & (qm <= 1)
                clips.append(1 - ok.mean())
                # unclipped: only valid where in range; use exact q via normal approx for out-of-range (rare); here clip anyway
                qp, qm = np.clip(qp, 0, 1), np.clip(qm, 0, 1)
            y = (rng.binomial(16, qp) - rng.binomial(16, qm)) / 16
            K = rng.binomial(m, r)
            res = endpoint_contrast_poly_cs(y, K, m, t, degree=2)
            if not res['ok']: fails += 1; continue
            ests.append(res['beta'][-1]); ses.append(res['se'][-1])
        ests, ses = np.array(ests), np.array(ses)
        print(name, m, 'n', n, 'mean sqrt(n)se/formula %.3f' % (np.mean(ses) * n ** 0.5 / sdf),
              'median %.3f' % (np.median(ses) * n ** 0.5 / sdf),
              'MC sd/formula %.3f' % (np.std(ests, ddof=1) * n ** 0.5 / sdf), 'mean est %.4f' % ests.mean(),
              'clipshare %.3f' % np.mean(clips), 'fails', fails, flush=True)
