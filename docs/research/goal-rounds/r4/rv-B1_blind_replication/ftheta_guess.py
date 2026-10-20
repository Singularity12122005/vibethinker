# Try to identify the undefined "F_theta" family from the quoted Hellinger numbers at m=128
from fractions import Fraction as Fr
import mpmath as mp
from affinity import betabin_pmf, twopoint_pmf, affinity, lecam, Fa
mp.mp.dps = 30
targets = {0.7:0.2419, 0.8:0.4518, 0.9:0.7156}
m=128
pa = [betabin_pmf(m,*Fa[t]) for t in range(2)]
def bound_for(pq):
    r0=affinity(pa[0],pq[0]); r1=affinity(pa[1],pq[1]); return float(lecam(r0,r1)[0])
def cand_pmfs(theta, kind):
    th = Fr(theta).limit_denominator(1000)
    out=[]
    for (a,b) in Fa:
        a,b=Fr(a),Fr(b); mu=a/(a+b); c=a+b
        if kind=="conc/theta":          # Beta(a/θ, b/θ)
            out.append(betabin_pmf(m,a/th,b/th))
        elif kind=="conc/theta^2":
            out.append(betabin_pmf(m,a/th**2,b/th**2))
        elif kind=="conc*theta":
            out.append(betabin_pmf(m,a*th,b*th))
        elif kind=="var*theta":         # var ratio θ: c'+1 = (c+1)/θ
            c2=(c+1)/th-1; out.append(betabin_pmf(m,mu*c2,(1-mu)*c2))
        elif kind=="var*theta^2":
            c2=(c+1)/th**2-1; out.append(betabin_pmf(m,mu*c2,(1-mu)*c2))
        elif kind=="mix_a_b":           # θ F_a + (1-θ) F_b
            from affinity import Fb
            t=len(out); pb=betabin_pmf(m,*Fb[t]); pa_=betabin_pmf(m,a,b)
            out.append([th*x+(1-th)*y for x,y in zip(pa_,pb)])
        elif kind=="mix_a_point":       # θ F_a + (1-θ) δ_mu
            pa_=betabin_pmf(m,a,b); pp=twopoint_pmf(m,[mu],[1])
            out.append([th*x+(1-th)*y for x,y in zip(pa_,pp)])
        elif kind=="shrink_point_theta": # r = θ r_a + (1-θ) μ  (Beta not closed; approximate by quadrature)
            out.append(None)
    return out
for kind in ["conc/theta","conc/theta^2","conc*theta","var*theta","var*theta^2","mix_a_b","mix_a_point"]:
    res={th: round(bound_for(cand_pmfs(th,kind)),4) for th in targets}
    print(kind, res, "targets", targets)
