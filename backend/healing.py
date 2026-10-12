"""Local gradient-domain texture healing with unchanged boundary pixels."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


def heal_patch(target, donor, selected):
    mask=np.asarray(selected,dtype=bool).copy()
    mask[[0,-1]]=False;mask[:,[0,-1]]=False
    ys,xs=np.where(mask)
    if not len(ys):return target.copy()
    indices=np.full(mask.shape,-1,dtype=int);indices[ys,xs]=np.arange(len(ys))
    rows=[];cols=[];values=[]
    rhs=np.zeros((len(ys),3),dtype=float)
    texture=np.asarray(donor,dtype=float);base=np.asarray(target,dtype=float)
    for i,(y,x) in enumerate(zip(ys,xs)):
        rows.append(i);cols.append(i);values.append(4)
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            yy,xx=y+dy,x+dx
            rhs[i]+=texture[y,x]-texture[yy,xx]
            j=indices[yy,xx]
            if j>=0:rows.append(i);cols.append(j);values.append(-1)
            else:rhs[i]+=base[yy,xx]
    solution=spsolve(coo_matrix((values,(rows,cols)),shape=(len(ys),len(ys))).tocsc(),rhs)
    if not np.isfinite(solution).all():raise RuntimeError('Invalid healing solution')
    result=np.asarray(target).copy()
    result[ys,xs]=np.round(np.clip(solution,0,255)).astype(np.uint8)
    return result
