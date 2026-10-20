import sys, glob
import numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/rereview_C1_blind_replication")
from nested import batch_test, t, NT, between_sd

for f in sorted(glob.glob("nested_*_4000x200_*.npz")):
    z = np.load(f)
    K32 = z['K32'].astype(float); O = K32.shape[0]
    rh = K32 / 32
    vw = rh[:, :NT].var(1) + rh[:, NT:].var(1)
    dm = rh[:, NT:].mean(1) - rh[:, :NT].mean(1)
    ok32, _, _ = batch_test(np.zeros_like(K32), K32, m=32)
    stats_ = {'hiVar': vw, 'loVar': -vw, 'hiDiff': dm, 'loDiff': -dm, 'hiMean': rh.mean(1), 'loMean': -rh.mean(1)}
    print(f, "P(PD at 32)=", ok32.mean())
    for key in ['rejR_HC1', 'rejR_CR1', 'npdR', 'wR']:
        R = z[key]; F = z[key.replace('R', 'F', 1) if key != 'npdR' else 'npdF'] if key != 'wR' else z['wF']
        if key.startswith('rej'):
            F = z[key.replace('rejR', 'rejF')]
        D = R - F
        sd, ucl = between_sd(D)
        line = [f"{key}: sig_delta={sd:.4f} UCL={ucl:.4f}"]
        rules = dict(stats_)
        rules['PD32'] = ok32.astype(float) + 1e-9 * np.random.default_rng(0).random(O)
        rules['notPD32'] = -rules['PD32']
        # split-sample oracle: rank by first 100 inner draws, evaluate on last 100
        orc = D[:, :100].mean(1)
        for pi in (0.1, 0.5):
            for name, s in list(rules.items()) + [('oracle_hi', orc), ('oracle_lo', -orc)]:
                if name in ('PD32', 'notPD32'):
                    sel = (ok32 if name == 'PD32' else ~ok32)
                    if pi == 0.5:
                        continue
                    # use natural probability
                else:
                    sel = s >= np.quantile(s, 1 - pi)
                ev = D[sel][:, 100:] if name.startswith('oracle') else D[sel]
                eff = ev.mean(); se = ev.mean(1).std(ddof=1) / np.sqrt(sel.sum())
                p = sel.mean()
                bound = ucl * np.sqrt((1 - p) / p)
                flag = " EXCEEDS" if abs(eff) > bound else ""
                if abs(eff) > 2.5 * se or flag:
                    line.append(f"  pi={p:.3f} {name}: {eff:+.4f}±{se:.4f} bound={bound:.4f}{flag}")
        print("\n".join(line))
