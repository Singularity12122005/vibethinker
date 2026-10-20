import numpy as np
from scipy.stats import beta
w=0.5
def mom(a,b,k): return beta(a,b).moment(k) if k>0 else 1.0
m0=[mom(20,80,k) for k in range(5)]; m1=[mom(25,75,k) for k in range(5)]
mx=[(1-w)*m0[k]+w*m1[k] for k in range(5)]
Q=np.array([[mx[i+j] for j in range(3)] for i in range(3)])
q=np.array([w*m1[k] for k in range(3)])
print("D=",w-q@np.linalg.solve(Q,q))
