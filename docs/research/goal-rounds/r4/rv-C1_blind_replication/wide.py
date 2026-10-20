import exact as E
from fractions import Fraction as F
import sympy
for name,(p0,p1) in {'w1':((F(10),F(40)),(F(25,2),F(75,2))),'w2':((F(15),F(60)),(F(75,4),F(225,4))),'w3':((F(10),F(40)),(F(25,2),F(75,2)))}.items():
    E.WORLDS['wide']=[p0,p1]
    s,_=E.share('wide',2)
    out=[]
    for g in E.GS.values():
        A,S,Sm,P=E.mats('wide',g); w=sympy.Matrix(A).inv()[3,:].T
        out.append(float(sympy.sqrt((w.T*sympy.Matrix(P)*w)[0]/(w.T*sympy.Matrix(S)*w)[0])))
    print(name,float(s),out)
