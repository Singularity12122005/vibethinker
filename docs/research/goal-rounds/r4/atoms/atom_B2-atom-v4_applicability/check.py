import sys, importlib.util, numpy as np, warnings
spec=importlib.util.spec_from_file_location("g",sys.argv[1]); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
rng=np.random.default_rng(0)
# G6-like: n=200, m=32 (and 128), type 0/1 and 1/2 coding, question clusters of size ~4, narrow non-Beta risk (two-point mixture)
bad=0; npd=0; tot=0
for m in (32,128):
  for p in (1,2,3):
    for rep in range(150):
      n=200; t=np.r_[np.zeros(100),np.ones(100)]
      r=np.where(t==1, rng.choice([0.22,0.28],n), rng.choice([0.18,0.22],n))
      K=rng.binomial(m,r)
      for tc in (t, t+1):
        cm=g.corrected_moment_matrix(K,m,tc,p)
        for y,cl in [(rng.normal(size=n),None),(np.full(n,np.nan),rng.integers(0,50,n)),(rng.binomial(16,0.3,n)/16-rng.binomial(16,0.5,n)/16,np.arange(n)//4),(np.full(n,1e308),list("x"*n))]:
          with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            o=g.endpoint_contrast_poly_cs(y,K,m,tc,p,cl) if cm["pd_ok"] else g.endpoint_contrast_poly_cs(y,K,m,tc,p,object())
          tot+=1
          if o["min_eig"]!=cm["min_eig"] or ((not cm["pd_ok"]) and o["ok"]) : bad+=1
          if not cm["pd_ok"]: npd+=1
print("total",tot,"mismatch",bad,"nonPD calls",npd)
