from fractions import Fraction as F
def two(atoms): return sum(w for r,w in atoms), sum(r*w for r,w in atoms), sum(r*r*w for r,w in atoms)
c0=[(F(81,505),F(101,201)),(F(6,25),F(100,201))]
c1=[(F(329,1616),F(1616,3491)),(F(29,100),F(1875,3491))]
print(two(c0), two(c1))
def beta2(a,b): return F(a,1)/(a+b), F(a*(a+1),(a+b)*(a+b+1))
print(beta2(20,80), beta2(25,75))
