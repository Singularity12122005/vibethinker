import numpy as np
A=np.array([[1.,2.],[2.,4.]])
for b in ([1,1],[np.nan,1],[np.inf,-np.inf],[0,0]):
    try: np.linalg.solve(A,np.array(b,float)); print(b,"no raise")
    except np.linalg.LinAlgError as e: print(b,"raise",e)
A=np.array([[1.,0.],[0.,1e-300]])
for b in ([1,1],[np.nan,1],[np.inf,-np.inf],[1e308,1e308]):
    try: print(b,np.linalg.solve(A,np.array(b,float)))
    except np.linalg.LinAlgError as e: print(b,"raise",e)
