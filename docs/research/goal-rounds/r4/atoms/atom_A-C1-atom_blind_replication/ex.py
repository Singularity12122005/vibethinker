import sympy as sp
from sympy import Rational as R, binomial
m=5
b0,b1,b2,bb=R(1,3),R(-2,1),R(3,2),R(7,10)
beta=sp.Matrix([b0,b1,b2,bb])
w1=R(2,5)
def ff(K,j): # falling factorial
    v=1
    for i in range(j): v*=(K-i)
    return v
U=lambda K,j: R(ff(K,j),ff(m,j))
def pieces(r,t,K):
    u=[U(K,j) for j in range(5)]
    M=sp.Matrix([[u[0],u[1],u[2],t],[u[1],u[2],u[3],t*u[1]],[u[2],u[3],u[4],t*u[2]],[t,t*u[1],t*u[2],t]])
    xm=sp.Matrix([u[0],u[1],u[2],t])  # m = xm*y
    return M,xm
def moments(F0,F1,sig2):
    # E over (t,r,K, eta) ; y=y0+eta ; psi = xm*y - M beta
    A=sp.zeros(4,4); B=sp.zeros(4,4); Epsi=sp.zeros(4,1); Exx=sp.zeros(4,4)
    for t,wt,F in [(0,1-w1,F0),(1,w1,F1)]:
        for r,pr in F:
            y0=b0+b1*r+b2*r**2+bb*t
            xt=sp.Matrix([1,r,r**2,t])
            Exx+=wt*pr*xt*xt.T
            for K in range(m+1):
                pk=binomial(m,K)*r**K*(1-r)**(m-K)
                M,xm=pieces(r,t,K)
                p=wt*pr*pk
                A+=p*M
                ps=xm*y0-M*beta
                Epsi+=p*ps
                B+=p*(ps*ps.T + sig2(r)*xm*xm.T)
    return A,B,Epsi,Exx
def analyze(F0,F1,sig2):
    A,B,Epsi,Exx=moments(F0,F1,sig2)
    assert A==Exx and Epsi==sp.zeros(4,1)
    Ai=A.inv(); V=(Ai*B*Ai.T)[3,3]
    Q=A[:3,:3]; q=A[:3,3]; D=A[3,3]-(q.T*Q.inv()*q)[0]; g=Q.inv()*q
    c=sp.Matrix([-g[0],-g[1],-g[2],1])
    Ephi2=(c.T*B*c)[0]
    return sp.nsimplify(V), sp.simplify(V-Ephi2/D**2), D
F0=[(R(1,10),R(1,4)),(R(3,10),R(1,2)),(R(1,2),R(1,4))]
F1=[(R(1,5),R(1,3)),(R(2,5),R(1,3)),(R(7,10),R(1,3))]
for name,s in [('const',lambda r:R(1,2)),('r^5',lambda r:r**5),('1+r',lambda r:1+r)]:
    V,diff,D=analyze(F0,F1,s); print(name,'V=',float(V),'V - Ephi2/D^2 =',diff)
# moment-matching pair for F1: 10 points, match moments 0..8
pts=[R(k,11) for k in range(1,11)]
Vd=sp.Matrix(9,10,lambda i,j: pts[j]**i)
c=Vd.nullspace()[0]; c=c/max(abs(x) for x in c)
eps=R(1,20)
Fa=[(p,R(1,10)) for p in pts]
Fb=[(pts[j],R(1,10)+eps*c[j]) for j in range(10)]
assert all(w>0 for _,w in Fb)
for k in range(12): print(k, sum(w*p**k for p,w in Fa)-sum(w*p**k for p,w in Fb), end='; ')
print()
for name,s in [('const',lambda r:R(1,2)),('r^5',lambda r:r**5),('r^1',lambda r:r)]:
    Va,_,Da=analyze(F0,Fa,s); Vb,_,Db=analyze(F0,Fb,s)
    print(name,'Da==Db',Da==Db,'Va-Vb=',Va-Vb, float(Va-Vb))
