"""Rigid eye alignment and conservative head/upper-shoulder framing."""
import math
import numpy as np
from PIL import Image


def safe_frame(eyes,face_height,head,shoulders,dimensions,zoom=1,offset_x=0,offset_y=0):
    fw,fh=dimensions;aspect=fw/fh
    cx,ey=np.mean(eyes,axis=0)
    eye_fraction=.42
    # 34 mm is a framing target for the estimated face, not a certification.
    target_face_mm=34 if dimensions==(50,60) else fh*.57
    nominal=face_height*fh/target_face_mm
    left=min(head[0],shoulders[0]);right=max(head[2],shoulders[2])
    bottom=max(head[3],shoulders[3]);top=head[1]
    minimum=max(2*(cx-left)/(.92*aspect),2*(right-cx)/(.92*aspect),
                (ey-top)/(.42-.045),(bottom-ey)/(1-.42-.035),1)
    height=max(nominal/zoom,minimum)
    width=height*aspect
    requested_cx=cx+offset_x/100*width
    requested_top=ey-eye_fraction*height+offset_y/100*height
    centre_min=right+width*.04-width/2
    centre_max=left-width*.04+width/2
    cx=float(np.clip(requested_cx,centre_min,centre_max))
    min_top=bottom-height+height*.035
    max_top=top-height*.045
    top_y=float(np.clip(requested_top,min_top,max_top))
    return (cx-width/2,top_y,cx+width/2,top_y+height),{
        'estimated_face_mm':round(face_height/height*fh,2),
        'eye_from_top_mm':round((ey-top_y)/height*fh,2),
        'hair_margin_mm':round((head[1]-top_y)/height*fh,2),
        'protection_limited_zoom':bool(nominal/zoom<minimum-.01),
        'head_bounds':list(map(float,head)),'shoulder_bounds':list(map(float,shoulders))}


def align_portrait(image,face,parser,dimensions,zoom=1,offset_x=0,offset_y=0):
    import cv2
    face=np.array(face,dtype=float)
    if face[-1]<.9:raise ValueError('Yüz hizalama güveni düşük. Daha net ve karşıdan çekilmiş bir fotoğraf seçin.')
    eyes=face[4:8].reshape(2,2);eyes=eyes[np.argsort(eyes[:,0])]
    angle=math.degrees(math.atan2(*(eyes[1]-eyes[0])[::-1]))
    if abs(angle)>15:raise ValueError('Baş eğimi fazla. Karşıdan ve baş dik olarak çekilmiş bir fotoğraf kullanın.')
    w,h=image.size
    native_alpha=np.asarray(image.convert('RGBA'))[...,3]>8
    x,y,fw,fh=face[:4]
    relevant_top=max(0,int(y-fh*.75));relevant_bottom=min(h,int(y+fh*1.55))
    input_edge_contact=bool(native_alpha[relevant_top:relevant_bottom,0].any() or
                            native_alpha[relevant_top:relevant_bottom,-1].any() or
                            (relevant_top==0 and native_alpha[0,max(0,int(x-fw)):min(w,int(x+2*fw))].any()))
    # One rigid rotation of the entire photograph; never warp the face itself.
    matrix=cv2.getRotationMatrix2D((w/2,h/2),angle,1)
    cos,sin=abs(matrix[0,0]),abs(matrix[0,1])
    nw,nh=math.ceil(w*cos+h*sin),math.ceil(h*cos+w*sin)
    matrix[0,2]+=nw/2-w/2;matrix[1,2]+=nh/2-h/2
    # Rotate premultiplied RGB so transparent background colours cannot bleed
    # into delicate hair during resampling.
    array=np.asarray(image.convert('RGBA')).astype(np.float32)/255
    array[...,:3]*=array[...,3:4]
    rotated=cv2.warpAffine(array,matrix,(nw,nh),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT)
    rotated=np.clip(rotated,0,1)
    rotated[...,:3]=np.divide(rotated[...,:3],rotated[...,3:4],out=np.zeros_like(rotated[...,:3]),where=rotated[...,3:4]>1e-6)
    image=Image.fromarray(np.round(np.clip(rotated,0,1)*255).astype(np.uint8))
    def transform(points):return np.asarray(points)@matrix[:,:2].T+matrix[:,2]
    eyes=transform(eyes)
    x,y,fw,fh=face[:4]
    corners=transform([[x,y],[x+fw,y],[x,y+fh],[x+fw,y+fh]])
    left,top=corners.min(0);right,bottom=corners.max(0)
    cx,ey=eyes.mean(0)
    cl,ct=max(0,int(cx-fw*1.5)),max(0,int(top-fh*.75))
    cr,cb=min(nw,int(cx+fw*1.5)),min(nh,int(bottom+fh*.75))
    roi=np.asarray(image)[ct:cb,cl:cr]
    labels=parser.labels(roi[...,:3])
    alpha=roi[...,3]>8
    yy,xx=np.indices(alpha.shape)
    # Semantic head selects the hair extent; native alpha extends protection to
    # fine strands the 512px parser cannot represent individually.
    head_mask=np.isin(labels,[1,2,3,4,5,6,7,8,10,11,12,13,17,18])&alpha
    head_mask &= (yy+ct<bottom+fh*.05)
    if head_mask.sum()<40:raise ValueError('Baş ve saç sınırı güvenle bulunamadı. Manuel kadraj kullanın.')
    ys,xs=np.where(head_mask)
    hair_top=float(ys.min()+ct)
    full_alpha=np.asarray(image)[...,3]>8
    hy0,hy1=max(0,int(hair_top-fh*.08)),min(nh,int(bottom)+1)
    ys,xs=np.where(full_alpha[hy0:hy1])
    head=(float(xs.min()),float(ys.min()+hy0),float(xs.max()+1),float(ys.max()+hy0+1))
    skin=(labels==1)&alpha&(xx+cl>cx-fw*.36)&(xx+cl<cx+fw*.36)&(yy+ct<bottom)
    sy,_=np.where(skin)
    face_height=float(np.quantile(sy,.99)-np.quantile(sy,.01)) if len(sy)>40 else float(fh)
    if face_height<fh*.65:face_height=float(fh)
    # Preserve the complete visible upper-shoulder outline, not the arms/hands
    # lower down the body. A passport frame ends at the upper chest.
    shoulder_top,shoulder_bottom=max(0,int(bottom+fh*.10)),min(nh,int(bottom+fh*.48)+1)
    sy,sx=np.where(full_alpha[shoulder_top:shoulder_bottom])
    if len(sx)>20:
        shoulders=(float(sx.min()),float(sy.min()+shoulder_top),float(sx.max()+1),float(sy.max()+shoulder_top+1))
    else:shoulders=(float(left),float(bottom),float(right),float(bottom+fh*.3))
    box,info=safe_frame(eyes,face_height,head,shoulders,dimensions,zoom,offset_x,offset_y)
    info.update({'rotation_degrees':round(angle,3),'eye_level_difference_px':round(float(abs(eyes[1,1]-eyes[0,1])),6),
                 'box':list(map(float,box)),'eyes':eyes.tolist()})
    info['face_size_target_mm']=[32,36] if dimensions==(50,60) else None
    info['face_size_warning']=bool(dimensions==(50,60) and not 32<=info['estimated_face_mm']<=36)
    info['source_edge_contact']=bool(input_edge_contact or head[0]<=1 or head[1]<=1 or head[2]>=nw-1 or shoulders[0]<=1 or shoulders[2]>=nw-1)
    return image,box,info
