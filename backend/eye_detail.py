"""Conservative native eye edge contrast, without restoration or warping."""
import numpy as np
from PIL import Image


def enhance_eyes(image, detections):
    import cv2
    source=np.asarray(image.convert('RGBA'))
    rgba=source.copy()
    count=0
    for face in detections:
        if face[-1]<.9 or face[2]<80 or face[3]<80:
            continue
        for point in np.array(face[4:8]).reshape(2,2):
            x,y=np.round(point).astype(int)
            rx,ry=max(4,round(face[2]*.095)),max(3,round(face[3]*.028))
            padding=4
            x0,y0=x-rx-padding,y-ry-padding
            x1,y1=x+rx+padding+1,y+ry+padding+1
            if x0<0 or y0<0 or x1>image.width or y1>image.height:
                continue
            # Work only on tiny native eye crops, even for a 40MP photograph.
            original=source[y0:y1,x0:x1]
            rgb=original[...,:3].astype(np.float32)
            luminance=rgb@np.array([.2126,.7152,.0722],np.float32)
            detail=-cv2.Laplacian(luminance,cv2.CV_32F,ksize=1)*.30
            gx=cv2.Sobel(luminance,cv2.CV_32F,1,0,ksize=3)/8
            gy=cv2.Sobel(luminance,cv2.CV_32F,0,1,ksize=3)/8
            gradient=np.hypot(gx,gy)
            lower=cv2.erode(luminance,np.ones((3,3),np.uint8))
            upper=cv2.dilate(luminance,np.ones((3,3),np.uint8))
            eye_mask=np.zeros(luminance.shape,np.uint8)
            cv2.ellipse(eye_mask,(x-x0,y-y0),(rx,ry),0,0,360,1,-1)
            # Inward gate controls contrast only; source pixels are not averaged.
            gate=np.clip(cv2.distanceTransform(eye_mask,cv2.DIST_L2,3)/3,0,1)
            eligible=(eye_mask>0)&(original[...,3]>=250)&(gradient>2)&(luminance>15)
            delta=np.clip(detail,-4,4)*gate
            delta=np.clip(luminance+delta,lower,upper)-luminance
            # Common RGB scale preserves channel ratios before native rounding.
            # Bound the largest channel change to four 8-bit levels.
            limit=4*luminance/np.maximum(rgb.max(axis=2),1)
            delta=np.clip(delta,-limit,limit)
            scale=1+delta/np.maximum(luminance,1)
            scale=np.minimum(scale,255/np.maximum(rgb.max(axis=2),1))
            values=np.round(np.clip(rgb*scale[...,None],0,255)).astype(np.uint8)
            rgba[y0:y1,x0:x1,:3][eligible]=values[eligible]
            count+=1
    return Image.fromarray(rgba),{'eyes':count,'eye_changed_pixels':int(np.any(rgba[...,:3]!=source[...,:3],axis=2).sum())}
