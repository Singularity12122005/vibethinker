import numpy as np
from scipy.stats import beta as B
w=0.5
def mom(a,b,k): return B(a,b).moment(k)
M=lambda k: w*mom(20,80,k)+(1-w)*mom(25,75,k)
Q=np.array([[M(i+j) for j in range(3)] for i in range(3)])
q=np.array([w*mom(25,75,k) for k in range(3)])
print("t=1 is Beta(25,75):", w-q@np.linalg.solve(Q,q))
q2=np.array([w*mom(20,80,k) for k in range(3)])
print("t=1 is Beta(20,80):", w-q2@np.linalg.solve(Q,q2))
