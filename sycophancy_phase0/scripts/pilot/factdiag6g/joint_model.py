"""冻结联合链的连续参数模型和共享潜在分量模型；纯CPU计算。"""
import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax, expit

SIZES=(4,5,4)


def observed_mask(labels):
    """-1是未知维度，似然对该维度求和，不充作负例或新结局。"""
    y=np.asarray(labels,dtype=int)
    if y.ndim!=2 or y.shape[1]!=3:raise ValueError('结局须有三列')
    mask=np.ones((len(y),*SIZES),dtype=float)
    for j,k in enumerate(SIZES):
        if np.any((y[:,j]<-1)|(y[:,j]>=k)):raise ValueError('结局类别超界')
        allowed=(y[:,j,None]<0)|(y[:,j,None]==np.arange(k))
        shape=[len(y),1,1,1];shape[j+1]=k
        mask*=allowed.reshape(shape)
    return mask


class Chain:
    def __init__(self,p):
        self.p=p;a,b,c=SIZES
        self.shapes=[(p,a),(p+a,b),(p+a+b,c)]
        self.n=sum(np.prod(s) for s in self.shapes)
        pieces=[]
        for shape in self.shapes:
            penalty=np.ones(shape);penalty[0]=0;pieces.append(penalty.ravel())
        self.penalty=np.concatenate(pieces)

    def unpack(self,theta):
        result=[];off=0
        for shape in self.shapes:
            n=int(np.prod(shape));result.append(theta[off:off+n].reshape(shape));off+=n
        return result

    def probability(self,theta,X):
        a,b,c=SIZES;p=self.p;w1,w2,w3=self.unpack(theta)
        p1=softmax(X@w1,axis=-1)
        p2=softmax((X@w2[:p])[:,None,:]+w2[p:][None,:,:],axis=-1)
        p3=softmax((X@w3[:p])[:,None,None,:]+w3[p:p+a][None,:,None,:]+
                   w3[p+a:][None,None,:,:],axis=-1)
        joint=p1[:,:,None,None]*p2[:,:,:,None]*p3
        return joint,(p1,p2,p3)

    def gradient(self,X,parts,posterior):
        """posterior已含该行权重与分量后验；返回负对数似然梯度。"""
        p1,p2,p3=parts
        marginal1=posterior.sum(axis=(2,3));marginal2=posterior.sum(axis=3)
        g1=p1*marginal1.sum(axis=1)[:,None]-marginal1
        g2=p2*marginal1[:,:,None]-marginal2
        g3=p3*marginal2[:,:,:,None]-posterior
        dw1=X.T@g1
        dw2=np.concatenate([X.T@g2.sum(axis=1),g2.sum(axis=0)],axis=0)
        dw3=np.concatenate([X.T@g3.sum(axis=(1,2)),g3.sum(axis=(0,2)),g3.sum(axis=(0,1))],axis=0)
        return np.concatenate([dw1.ravel(),dw2.ravel(),dw3.ravel()])


class JointModel:
    def __init__(self,p,gate_columns=0):
        self.chain=Chain(p);self.gate_columns=gate_columns
        self.components=2 if gate_columns else 1
        self.n=self.components*self.chain.n+gate_columns
        gate_penalty=np.ones(gate_columns)
        if gate_columns:gate_penalty[0]=0
        self.penalty=np.concatenate([*[self.chain.penalty]*self.components,gate_penalty])

    def distribution(self,theta,X,gate=None,parts=False):
        n=self.chain.n
        chains=[self.chain.probability(theta[z*n:(z+1)*n],X) for z in range(self.components)]
        if self.components==2:
            if gate is None or gate.shape[1]!=self.gate_columns:raise ValueError('混合比例输入不符')
            pi=expit(gate@theta[2*n:]);weights=[pi,1-pi]
        else:weights=[np.ones(len(X))]
        joint=sum(w[:,None,None,None]*v[0] for w,v in zip(weights,chains))
        return (joint,chains,weights) if parts else joint

    def loss_gradient(self,theta,X,mask,weights,penalty,gate=None):
        joint,chains,mix=self.distribution(theta,X,gate,parts=True)
        mass=(joint*mask).sum(axis=(1,2,3))
        if np.any(mass<=0) or not np.all(np.isfinite(mass)):raise FloatingPointError('联合概率下溢或非有限')
        objective=-weights@np.log(mass)+.5*penalty*np.sum(self.penalty*theta*theta)
        posterior=[w[:,None,None,None]*v[0]*mask*(weights/mass)[:,None,None,None]
                   for w,v in zip(mix,chains)]
        grads=[self.chain.gradient(X,v[1],post) for v,post in zip(chains,posterior)]
        if self.components==2:
            grads.append(gate.T@(weights*mix[0]-posterior[0].sum(axis=(1,2,3))))
        grad=np.concatenate(grads)+penalty*self.penalty*theta
        return float(objective),grad

    def fit(self,X,labels,weights,penalty,gate=None,seed=20261111):
        X=np.asarray(X,dtype=float);weights=np.asarray(weights,dtype=float)
        mask=observed_mask(labels)
        if len(X)!=len(mask) or weights.shape!=(len(X),):raise ValueError('拟合输入长度不符')
        if not np.isclose(weights.sum(),1) or np.any(weights<0):raise ValueError('权重须非负且和为1')
        rng=np.random.default_rng(seed);starts=[np.zeros(self.n)]
        if self.components==2:
            starts[0]+=rng.normal(0,1e-4,self.n)
            starts +=[rng.normal(0,.05,self.n),rng.normal(0,.15,self.n)]
        results=[]
        for initial in starts:
            result=minimize(lambda t:self.loss_gradient(t,X,mask,weights,penalty,gate),initial,
                method='L-BFGS-B',jac=True,options=dict(maxiter=500,ftol=1e-9,gtol=1e-6))
            results.append(result)
        chosen=min(results,key=lambda r:r.fun)
        return dict(theta=chosen.x.tolist(),objective=float(chosen.fun),converged=bool(chosen.success),
            message=str(chosen.message),iterations=int(chosen.nit),penalty=penalty,
            starts=[dict(objective=float(r.fun),converged=bool(r.success),iterations=int(r.nit)) for r in results])


def log_scores(distribution,labels):
    y=np.asarray(labels);mask=observed_mask(y)
    joint=np.log((distribution*mask).sum(axis=(1,2,3)))
    joint[np.all(y<0,axis=1)]=np.nan
    marginal=[]
    for axis in range(3):
        keep=axis+1;summed=tuple(i for i in (1,2,3) if i!=keep)
        p=distribution.sum(axis=summed);score=np.full(len(y),np.nan)
        known=y[:,axis]>=0;score[known]=np.log(p[np.where(known)[0],y[known,axis]])
        marginal.append(score)
    return dict(joint=joint,y1=marginal[0],y2=marginal[1],y3=marginal[2])
