"""Native-resolution NAFNet detail transfer, without replacing face texture."""
import hashlib
import threading
from pathlib import Path
import numpy as np

REVISION = '47534e27c9851bb1128ccc0102f1145e27f23f98'
SHA256 = '07263f416febecce10193dd648e950b22e397cf521eedab1a114ef77b2bc9587'
URL = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models/deblurring_nafnet/deblurring_nafnet_2025may.onnx'


def transfer_detail(source, restored, eligible, strength=70, features=None):
    """Only transfer stronger coherent luminance edges; preserve source colour."""
    import cv2
    coefficients=np.array([.2126,.7152,.0722],np.float32)
    light=source.astype(np.float32)@coefficients
    target=restored.astype(np.float32)@coefficients
    gx=cv2.Sobel(light,cv2.CV_32F,1,0)/8;gy=cv2.Sobel(light,cv2.CV_32F,0,1)/8
    tx=cv2.Sobel(target,cv2.CV_32F,1,0)/8;ty=cv2.Sobel(target,cv2.CV_32F,0,1)/8
    xx=cv2.boxFilter(gx*gx,-1,(5,5));yy=cv2.boxFilter(gy*gy,-1,(5,5));xy=cv2.boxFilter(gx*gy,-1,(5,5))
    coherence=np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-6)
    # The raw model smooths skin/hair. Reject those pixels outright, retain
    # original pores/colour, and accept only aligned stronger existing edges.
    selected=eligible&(coherence>.5)&(np.hypot(gx,gy)>2)&(np.hypot(tx,ty)>np.hypot(gx,gy)*1.08)&((gx*tx+gy*ty)>0)
    difference=target-light
    selected &= np.abs(difference)<24
    amount=np.clip(strength/100,0,1)
    delta=np.clip(difference*(.5+amount),-18*amount,18*amount)
    lower=cv2.erode(source,np.ones((3,3),np.uint8));upper=cv2.dilate(source,np.ones((3,3),np.uint8))
    output=source.copy()
    changed=np.round(np.clip(source.astype(float)+delta[...,None],lower,upper)).astype(np.uint8)
    output[selected]=changed[selected]
    return output


class NaturalDeblur:
    def __init__(self, cache: Path):
        self.cache=cache;self.session=None;self.lock=threading.Lock()

    def apply(self, rgb, eligible, strength=70, features=None):
        import onnxruntime as ort
        import requests
        with self.lock:
            if self.session is None:
                path=self.cache/'face'/'nafnet.onnx';path.parent.mkdir(parents=True,exist_ok=True)
                if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
                    response=requests.get(URL,timeout=(10,120));response.raise_for_status()
                    if hashlib.sha256(response.content).hexdigest()!=SHA256:raise RuntimeError('NAFNet checksum mismatch')
                    temporary=path.with_suffix('.tmp');temporary.write_bytes(response.content);temporary.replace(path)
                options=ort.SessionOptions();options.log_severity_level=3;options.intra_op_num_threads=4
                self.session=ort.InferenceSession(str(path),options,providers=['CPUExecutionProvider'])
            h,w=rgb.shape[:2];sums=np.zeros_like(rgb,dtype=np.float32);weights=np.zeros((h,w),np.float32)
            from .matting import tile_positions
            for y in tile_positions(h,384,96):
                for x in tile_positions(w,384,96):
                    patch=rgb[y:y+384,x:x+384];ph,pw=patch.shape[:2]
                    if not eligible[y:y+ph,x:x+pw].any():continue
                    padded=np.pad(patch,((0,max(384,((ph+15)//16)*16)-ph),
                                         (0,max(384,((pw+15)//16)*16)-pw),(0,0)),mode='reflect')
                    tensor=padded.transpose(2,0,1)[None].astype(np.float32)/255
                    prediction=self.session.run(None,{self.session.get_inputs()[0].name:tensor})[0][0].transpose(1,2,0)[:ph,:pw]*255
                    if not np.isfinite(prediction).all():raise RuntimeError('Invalid NAFNet output')
                    weight=np.maximum(np.outer(np.hanning(ph+2)[1:-1],np.hanning(pw+2)[1:-1]),.001)
                    sums[y:y+ph,x:x+pw]+=prediction*weight[...,None];weights[y:y+ph,x:x+pw]+=weight
            restored=sums/np.maximum(weights[...,None],.001)
            return transfer_detail(rgb,restored,eligible,strength,features)
