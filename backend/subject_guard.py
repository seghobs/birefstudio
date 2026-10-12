"""Protect source eye colour and confidently opaque subject interiors."""
import numpy as np
from PIL import Image
from scipy.ndimage import minimum_filter


def protect_subject(source, result, detections=()):
    import cv2
    original=np.asarray(source.convert('RGBA'))
    output=np.asarray(result.convert('RGBA')).copy()
    if original.shape!=output.shape:raise ValueError('Subject guard dimensions differ')
    alpha=output[...,3]
    # Interior only: never harden the soft hair contour or fill background gaps.
    core=(alpha>=250)&(minimum_filter(alpha,size=5,mode='constant',cval=0)>=240)
    guard=core.copy()
    for detection in detections:
        x,y,w,h=detection[:4]
        if len(detection)<15 or detection[14]<.9 or w<40 or h<40:continue
        for px,py in np.asarray(detection[4:8]).reshape(2,2):
            if not (x<=px<=x+w and y<=py<=y+h):continue
            rx=max(3,round(w*.13));ry=max(3,round(h*.065))
            left,top=max(0,int(np.ceil(x)),round(px)-rx),max(0,int(np.ceil(y)),round(py)-ry)
            right,bottom=min(source.width,int(x+w),round(px)+rx+1),min(source.height,int(y+h),round(py)+ry+1)
            yy,xx=np.ogrid[top:bottom,left:right]
            eye=((xx-px)/rx)**2+((yy-py)/ry)**2<=1
            area=alpha[top:bottom,left:right]
            # Reject eye detections on predominantly missing/background regions.
            if not eye.any() or np.mean(area[eye]>=128)<.75:continue
            guard[top:bottom,left:right]|=eye
    output[guard]=original[guard]
    return Image.fromarray(output)
