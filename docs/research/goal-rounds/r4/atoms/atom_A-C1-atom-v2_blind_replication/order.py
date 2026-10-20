import sympy as sp
r,s2=sp.symbols('r s2'); b0,b1,b2,bb,g0,g1,g2,e=sp.symbols('b0 b1 b2 bb g0 g1 g2 e')
def ff(K,j):
    v=1
    for i in range(j): v*=(K-i)
    return v
for m in (4,5,7):
  for t in (0,1):
    tot=0
    for K in range(m+1):
        pk=sp.binomial(m,K)*r**K*(1-r)**(m-K)
        U=[sp.Rational(ff(K,j),ff(m,j)) for j in range(5)]
        y=b0+b1*r+b2*r**2+bb*t+e
        th=[b0,b1,b2,bb]
        M=sp.Matrix([[U[0],U[1],U[2],t],[U[1],U[2],U[3],t*U[1]],[U[2],U[3],U[4],t*U[2]],[t,t*U[1],t*U[2],t]])
        psi=sp.Matrix([U[0]*y,U[1]*y,U[2]*y,t*y])-M*sp.Matrix(th)
        phi=psi[3]-g0*psi[0]-g1*psi[1]-g2*psi[2]
        ph2=sp.expand(phi**2)
        # E[e|.]=0, E[e^2|.]=s2
        ph2=ph2.subs(e**2,s2).subs(e,0)
        tot+=pk*ph2
    tot=sp.expand(tot)
    P=sp.Poly(tot,r)
    s2part=sp.Poly(sp.expand(tot.coeff(s2,1)),r); rest=sp.Poly(sp.expand(tot.coeff(s2,0)),r)
    print(m,t,"deg nonsigma",rest.degree(),"deg sigma-part",s2part.degree(), "s2 power>1?",sp.degree(tot,s2))
