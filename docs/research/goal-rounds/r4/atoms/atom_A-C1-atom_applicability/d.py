import numpy as np
from scipy import stats
def mom(a,b,k): return stats.beta(a,b).moment(k)
w=[.5,.5]; par=[(20,80),(25,75)]
Q=np.zeros((3,3)); q=np.zeros(3)
for wt,(a,b),t in zip(w,par,[0,1]):
    M=np.array([[mom(a,b,i+j) if i+j>0 else 1 for j in range(3)] for i in range(3)])
    Q+=wt*M
    if t: q+=wt*M[0]
print("D=",0.5-q@np.linalg.solve(Q,q), "cond(Q)=",np.linalg.cond(Q))
