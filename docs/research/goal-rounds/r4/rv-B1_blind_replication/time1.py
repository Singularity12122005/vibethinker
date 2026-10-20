import time
from lrtest import *
A=("beta",Fa)
t=time.time(); g,res=grid_min(32,A,("beta",Fb)); print("grid m=32 Fb",g,res,time.time()-t,flush=True)
t=time.time(); print("MC", mc_min(32,A,("beta",Fb),200000,seed=1), time.time()-t,flush=True)
