from rep import *
A=('beta',FA); B=('beta',FB); Cc=('mix',C2)
for name,W,m in [('FB',B,32),('C2',Cc,32),('C2',Cc,128)]:
    pa=pmfs(A,m); pb=pmfs(W,m)
    res=[np_exact(pa,pb,N=500000,seed=s) for s in range(8)]
    r=np.array([[x[0],x[2],x[4]] for x in res])
    print(name,m,r.mean(0), r.std(0)/np.sqrt(8))
