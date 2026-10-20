# discretization sensitivity of grid TV at m=32 (Fb, Fc2) and the corollary arithmetic
from lrtest import *
A=("beta",Fa)
for name,w in (("Fb",("beta",Fb)),("Fc2",("two",Fc2))):
    for d in (2e-4,1e-4,5e-5,2.5e-5):
        g,res=grid_min(32,A,w,delta=d)
        print(f"m=32 {name} delta={d:g}: min error sum={g:.5f}  TV={1-g:.5f}  availability bound TV+0.05={1-g+0.05:.4f}",flush=True)
