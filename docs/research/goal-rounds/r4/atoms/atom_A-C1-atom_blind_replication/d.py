from fractions import Fraction as Fr
import sympy as sp
def bm(a,b,k):
    v=Fr(1)
    for i in range(k): v*=Fr(a+i,a+b+i)
    return v
w1=Fr(1,2)
mom=lambda k: (1-w1)*bm(20,80,k)+w1*bm(25,75,k)
Q=sp.Matrix(3,3,lambda i,j: sp.Rational(mom(i+j).numerator,mom(i+j).denominator))
q=sp.Matrix([sp.Rational(w1*bm(25,75,k)) for k in range(3)])
D=sp.Rational(w1)-(q.T*Q.inv()*q)[0]
print(D, float(D))
