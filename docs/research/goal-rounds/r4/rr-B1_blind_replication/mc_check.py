import sys, numpy as np
sys.path.insert(0, '.')
import b1_replicate as B
m = 32; N = 400000
Wa = B.world('a', m); Wb = B.world('b', m)
L = [np.log(np.array([float(x) for x in Wa[t]])) - np.log(np.array([float(x) for x in Wb[t]])) for t in range(2)]
rng = np.random.default_rng(777)
def sim(W):
    tot = np.zeros(N)
    for t in range(2):
        p = np.array([float(x) for x in W[t]]); p /= p.sum()
        cnt = rng.multinomial(100, p, size=N)
        tot += cnt @ L[t]
    return tot
La = sim(Wa); Lb = sim(Wb)
e = (La <= 0).mean() + (Lb > 0).mean()
se = np.sqrt((La <= 0).mean()*(1-(La <= 0).mean())/N + (Lb > 0).mean()*(1-(Lb > 0).mean())/N)
print('MC NP error sum', e, 'SE', se)
