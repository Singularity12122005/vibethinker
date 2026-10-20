import sys, json
sys.path.insert(0, '.')
import b1_replicate as B
m = int(sys.argv[1]); w = sys.argv[2]; h = float(sys.argv[3]); eps = float(sys.argv[4])
Wa = B.world('a', m); Wb = B.world(w, m)
res = dict(m=m, world=w, h=h, eps=eps, **B.hell(Wa, Wb))
res.update(B.tv(Wa, Wb, h=h, eps=eps))
print(json.dumps(res), flush=True)
