from rep import *
A=('beta',FA); B=('beta',FB); Cc=('mix',C2)
for m in [32,128,512]:
    pa,pb,bd=report('FA-FB',A,B,m)
    print('  NP', np_exact(pa,pb,N=200000))
for m in [32,128]:
    pa,pb,bd=report('FA-C2',A,Cc,m)
    print('  NP', np_exact(pa,pb,N=200000))
# point mass at means
Cpt=('mix',[[(Fr(1,5),1)],[(Fr(1,4),1)]])
pa,pb,bd=report('FA-Cpoint',A,Cpt,32)
print('  NP', np_exact(pa,pb,N=200000))
