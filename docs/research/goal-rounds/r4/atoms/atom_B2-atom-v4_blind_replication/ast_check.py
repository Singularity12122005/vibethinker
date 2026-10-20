import ast
src=open("/tmp/claude-0/-home-user-vibethinker/f0ffafd6-4063-5255-a6b2-eb18152ed489/scratchpad/r4_worktree/sycophancy_phase0/src/sycophancy_phase0/analysis/g6_iv.py").read()
tree=ast.parse(src)
for f in tree.body:
    if isinstance(f,ast.FunctionDef) and f.name in("endpoint_contrast_poly_cs","corrected_moment_matrix"):
        names=sorted({n.id for n in ast.walk(f) if isinstance(n,ast.Name)})
        print(f.name, names)
        if f.name=="endpoint_contrast_poly_cs":
            for st in f.body:
                used={n.id for n in ast.walk(st) if isinstance(n,ast.Name)}
                print(st.lineno, type(st).__name__, sorted(used & {"y","delta_hat","cluster"}))
