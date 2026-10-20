"""Independent brute force of sup beta' Omega beta over {osc(b1 r + b2 r^2) <= 2} on a dense 2D grid (no boundary argument)."""
import sys, numpy as np
sys.path.insert(0, "/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/goal_rounds/r4/A__Overlap-and-PD-margin_certificate_from_pilot_U-statistics__upper_bound__sufficiency_direction_")
from route_a_lib import beta_moments, first_order
WORLDS = {"narrow": ((20, 80), (25, 75)), "halfvar": ((40.5, 162.0), (50.6, 151.8)), "wide": ((2, 8), (2.5, 7.5))}
rs = np.linspace(0, 1, 2001)
b1 = np.linspace(-12, 12, 1201); b2 = np.linspace(-12, 12, 1201)
B1, B2 = np.meshgrid(b1, b2, indexing="ij")
# osc on grid of r (exact for quadratics up to grid resolution; vertex handled analytically below)
def osc(B1, B2):
    v0 = np.zeros_like(B1); v1 = B1 + B2
    with np.errstate(divide="ignore", invalid="ignore"):
        rv = np.where(B2 != 0, -B1 / (2 * B2), -1.0)
    ins = (rv > 0) & (rv < 1)
    vv = np.where(ins, B1 * rv + B2 * rv ** 2, 0.0)
    mx = np.maximum(np.maximum(v0, v1), np.where(ins, vv, -np.inf)); mn = np.minimum(np.minimum(v0, v1), np.where(ins, vv, np.inf))
    return mx - mn
adm = osc(B1, B2) <= 2.0
for wn, (ab0, ab1) in WORLDS.items():
    mu0, mu1 = beta_moments(*ab0), beta_moments(*ab1)
    for m in (32, 128):
        fo = first_order(mu0, mu1, 0.5, m, 200, sup_g=True)
        Om = np.array(fo["Omega"], float)
        ev = np.linalg.eigvalsh(Om)
        q = Om[0, 0] * B1 ** 2 + 2 * Om[0, 1] * B1 * B2 + Om[1, 1] * B2 ** 2
        q = np.where(adm, q, -np.inf)
        i = np.unravel_index(np.argmax(q), q.shape)
        print(f"{wn:7s} m={m:3d}: Omega eig={ev}, lib sup={fo['term_g']:.6e} at b*={np.round(fo['beta_star'],3)}; grid sup={q[i]:.6e} at ({B1[i]:.2f},{B2[i]:.2f}); check corners: (-8,8)->{Om[0,0]*64-2*Om[0,1]*64+Om[1,1]*64:.6e}, (2,0)->{Om[0,0]*4:.6e}, (0,2)->{Om[1,1]*4:.6e}, (-2,0)... symmetric")
