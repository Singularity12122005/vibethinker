from fractions import Fraction as Fr
import sympy as sp, itertools, numpy as np

def beta_mom(a,b,k):
    v=Fr(1)
    for i in range(k): v*=Fr(a+i,a+b+i)
    return v
def Dval(mom0,mom1,w1):
    w0=1-w1
    E=lambda k: w0*mom0(k)+w1*mom1(k)
    Q=sp.Matrix(3,3,lambda i,j: sp.Rational(E(i+j)))
    q=sp.Matrix([sp.Rational(w1*mom1(k)) for k in range(3)])
    return sp.Rational(w1)-(q.T*Q.inv()*q)[0], Q, q
D,Q,q=Dval(lambda k:beta_mom(20,80,k),lambda k:beta_mom(25,75,k),Fr(1,2))
print("D exact",D, float(D))

# Exact asymptotic variance for discrete F_t: full sandwich vs D^-2 E[phi^2]
def ff(K,j):
    v=1
    for i in range(j): v*=(K-i)
    return v
def sandwich(supp, w1, m, beta, sig2):
    # supp: dict t-> list of (r, prob)
    b0,b1,b2,bb=beta; th=sp.Matrix([b0,b1,b2,bb])
    A=sp.zeros(4,4); B=sp.zeros(4,4)
    Ezz=sp.zeros(4,4)
    for t,lst in supp.items():
        wt = w1 if t==1 else 1-w1
        for r,p in lst:
            Ezz += wt*p*sp.Matrix([1,r,r**2,t])*sp.Matrix([[1,r,r**2,t]])
            for K in range(m+1):
                pk=sp.binomial(m,K)*r**K*(1-r)**(m-K)
                U=[sp.Rational(ff(K,j),ff(m,j)) for j in range(5)]
                M=sp.Matrix([[U[0],U[1],U[2],t],[U[1],U[2],U[3],t*U[1]],[U[2],U[3],U[4],t*U[2]],[t,t*U[1],t*U[2],t]])
                mu=b0+b1*r+b2*r**2+bb*t
                # y = mu + eta with eta=+-s (sym two-point), s^2=sig2(r)
                s=sp.sqrt(sig2(r))
                for e in (s,-s):
                    y=mu+e
                    mv=sp.Matrix([U[0]*y,U[1]*y,U[2]*y,t*y])
                    psi=mv-M*th
                    w=wt*p*pk/2
                    A+=w*M; B+=w*psi*psi.T
    Ai=A.inv()
    V=sp.simplify((Ai*B*Ai.T)[3,3])
    Qx=Ezz[:3,:3]; qq=Ezz[:3,3]; Dd=Ezz[3,3]-(qq.T*Qx.inv()*qq)[0]
    g=Qx.inv()*qq
    # phi second moment = (-g',1) B (-g',1)'
    c=sp.Matrix([-g[0],-g[1],-g[2],1])
    V2=sp.simplify((c.T*B*c)[0]/Dd**2)
    return sp.nsimplify(V), V2, sp.simplify(A-Ezz)
R=sp.Rational
supp={0:[(R(1,10),R(1,3)),(R(1,4),R(1,3)),(R(1,2),R(1,3))],1:[(R(1,5),R(1,2)),(R(3,10),R(1,4)),(R(7,10),R(1,4))]}
V,V2,diff=sandwich(supp,R(1,2),4,(R(1,3),R(2),R(-1),R(1,2)),lambda r: R(1,4)+r)
print("sandwich",V," formula",V2," equal",sp.simplify(V-V2)==0," E[M]-E[zz']=0",diff==sp.zeros(4,4))
