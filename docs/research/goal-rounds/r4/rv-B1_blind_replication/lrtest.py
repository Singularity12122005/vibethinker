# Independent NP/LR-test minimum: 1 - TV(P_a, P_b) for product of 100 type-0 + 100 type-1 beta-binomial counts.
# (1) Monte Carlo of the LR test, (2) deterministic grid convolution of the log-LR sum distribution.
import sys, numpy as np
from fractions import Fraction as Fr
from affinity import betabin_pmf, twopoint_pmf, Fa, Fb, Fc2
from math import comb

def ftheta(theta):
    th=Fr(theta)
    out=[]
    for (a,b) in Fa:
        a,b=Fr(a),Fr(b); mu=a/(a+b); c2=(a+b+1)/th-1
        out.append((mu*c2,(1-mu)*c2))
    return out

def pmfs(m, world):
    kind, par = world
    if kind=="beta": return [betabin_pmf(m,*par[t]) for t in range(2)]
    if kind=="two":  return [twopoint_pmf(m,*par[t]) for t in range(2)]

def sample_counts(rng, m, world, N, n=100):
    kind, par = world
    out=[]
    for t in range(2):
        if kind=="beta":
            a,b = float(par[t][0]), float(par[t][1])
            r = rng.beta(a,b,size=(N,n))
        else:
            atoms=np.array([float(x) for x in par[t][0]]); w=np.array([float(x) for x in par[t][1]])
            r = atoms[rng.choice(len(atoms), size=(N,n), p=w)]
        out.append(rng.binomial(m, r))
    return out

def mc_min(m, worldA, worldB, N, seed, n=100):
    rng=np.random.default_rng(seed)
    pa=pmfs(m,worldA); pb=pmfs(m,worldB)
    v=[np.array([float(np.log(float(pb[t][k]/pa[t][k]))) for k in range(m+1)]) for t in range(2)]
    def S(counts): return v[0][counts[0]].sum(1)+v[1][counts[1]].sum(1)
    errA=errB=0; done=0
    chunk=50000
    while done<N:
        c=min(chunk,N-done)
        Sa=S(sample_counts(rng,m,worldA,c,n)); Sb=S(sample_counts(rng,m,worldB,c,n))
        errA += np.sum(Sa>=0)     # under A, LR test does NOT certify when p_b>=p_a (ties -> not certify)
        errB += np.sum(Sb<0)      # under B, certifies when p_a>p_b
        done+=c
    pA=errA/N; pB=errB/N
    se=np.sqrt(pA*(1-pA)/N + pB*(1-pB)/N)
    return pA+pB, se

def grid_min(m, worldA, worldB, delta=1e-4, n=100, tail=1e-18):
    pa=pmfs(m,worldA); pb=pmfs(m,worldB)
    tot = {}
    for side, wts in (("A",pa),("B",pb)):
        dist=None  # (offset, array)
        for t in range(2):
            v=np.array([float(np.log(float(pb[t][k]/pa[t][k]))) for k in range(m+1)])
            idx=np.rint(v/delta).astype(np.int64); w=np.array([float(x) for x in wts[t]])
            keep=w>0; idx=idx[keep]; w=w[keep]
            lo=idx.min(); idx=idx-lo  # shift
            cur=np.zeros(1); cur[0]=1.0; off=0
            for _ in range(n):
                new=np.zeros(len(cur)+idx.max())
                for i,wk in zip(idx,w): new[i:i+len(cur)]+=wk*cur
                off += lo
                # prune tails
                cs=np.cumsum(new); L=np.searchsorted(cs,tail); R=np.searchsorted(cs,cs[-1]-tail)+1
                off += L; cur=new[L:R]
            if dist is None: dist=(off,cur)
            else:
                o2,c2=dist; conv=np.convolve(c2,cur); dist=(o2+off,conv)
        tot[side]=dist
    # P(S<0): indices with offset+i < 0
    res={}
    for side,(off,arr) in tot.items():
        nneg = max(0, min(len(arr), -off))      # number of entries with index < 0
        res[side]=(arr[:nneg].sum(), arr.sum())
    pA_cert=res["A"][0]; pB_cert=res["B"][0]
    return (1-pA_cert)+pB_cert, res

if __name__=="__main__":
    A=("beta",Fa)
    worlds={"Fb":("beta",Fb),"Fc2":("two",Fc2),"Fc":("two",[([Fr(1,5)],[1]),([Fr(1,4)],[1])]),
            "F0.7":("beta",ftheta(Fr(7,10))),"F0.8":("beta",ftheta(Fr(8,10))),"F0.9":("beta",ftheta(Fr(9,10)))}
    plan=[(32,"Fb",0.5210),(32,"Fc2",0.8537),(32,"Fc",0.1735),(128,"Fb",0.0967),(128,"Fc2",0.1638),
          (128,"F0.9",0.7721),(128,"F0.8",0.5499),(128,"F0.7",0.3547),(512,"Fb",0.0060),(512,"F0.8",0.3561),(512,"F0.9",0.6581)]
    N=int(sys.argv[1]) if len(sys.argv)>1 else 200000
    for m,name,claimed in plan:
        g,res=grid_min(m,A,worlds[name])
        mc,se=mc_min(m,A,worlds[name],N,seed=12345+m)
        print(f"m={m:4d} Fa vs {name:5s}: claimed={claimed:.4f}  grid(delta=1e-4)={g:.5f}  MC(N={N})={mc:.4f} (SE {se:.4f})  z={(mc-claimed)/max(se,1e-9):+.2f}", flush=True)
