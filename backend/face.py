"""Opt-in, local texture-patch retouching; no generative face reconstruction."""
import hashlib
import threading
from pathlib import Path
import numpy as np
from PIL import Image
from .healing import heal_patch

YUNET_REVISION = "26cc381e4d2594bb9f47a26eb8fd96c94a13660d"
YUNET_URL = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{YUNET_REVISION}/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


class FaceRetoucher:
    def __init__(self, cache: Path):
        self.cache = cache
        self.detector = None
        self.lock = threading.Lock()
        from .deblur import NaturalDeblur
        self.deblur = NaturalDeblur(cache)
        from .blemish_detector import BlemishDetector
        self.spot_detector=BlemishDetector(cache)

    def detect(self, rgb):
        with self.lock:
            return self._detect(rgb)

    def _detect(self, rgb):
        import cv2
        import requests
        path = self.cache / "face" / "yunet.onnx"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != YUNET_SHA256:
            response = requests.get(YUNET_URL, timeout=(10,60))
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != YUNET_SHA256:
                raise RuntimeError("Face detector checksum mismatch")
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(response.content)
            temporary.replace(path)
        scale = min(1.,960/max(rgb.shape[:2]))
        resized = cv2.resize(rgb,(round(rgb.shape[1]*scale),round(rgb.shape[0]*scale)))
        if self.detector is None:
            self.detector = cv2.FaceDetectorYN.create(str(path),"",(resized.shape[1],resized.shape[0]),.8,.3,1000)
        self.detector.setInputSize((resized.shape[1],resized.shape[0]))
        _, detections = self.detector.detect(cv2.cvtColor(resized,cv2.COLOR_RGB2BGR))
        if detections is None:
            return []
        detections[:,:14] /= scale
        return detections.tolist()

    def apply(self, image, clean=False, sharpen=False, spots=True, strength=70):
        if not clean and not sharpen:
            return image.copy(), {"faces":0,"spots":0,"changed_pixels":0,"message":"Yüz işlemi kapalı"}
        import cv2
        from scipy.ndimage import distance_transform_edt
        rgba = np.asarray(image.convert("RGBA"))
        original = rgba[...,:3].copy()
        output = original.copy()
        report = {"faces":0,"spots":0,"changed_pixels":0,"message":""}
        for detection in self.detect(original):
            x,y,w,h = detection[:4]
            if w < 40 or h < 40:
                continue
            left,top = max(0,int(x)),max(0,int(y))
            right,bottom = min(image.width,int(x+w+1)),min(image.height,int(y+h+1))
            if right-left < 40 or bottom-top < 40:
                continue
            rgb = original[top:bottom,left:right].copy()
            alpha = rgba[top:bottom,left:right,3]
            points = np.asarray(detection[4:14]).reshape(5,2)-[left,top]
            fw,fh = right-left,bottom-top
            safe = np.zeros((fh,fw),dtype=np.uint8)
            cv2.ellipse(safe,(round(fw*.5),round(fh*.50)),(round(fw*.37),round(fh*.44)),0,0,360,1,-1)
            # Eyes, brows, nostrils, lips, moustache and jaw are protected.
            for point in points[:2]:
                px,py=np.round(point).astype(int)
                cv2.rectangle(safe,(px-round(fw*.18),py-round(fh*.13)),
                              (px+round(fw*.18),py+round(fh*.07)),0,-1)
            eye_min=np.floor(points[:2].min(axis=0)).astype(int)
            eye_max=np.ceil(points[:2].max(axis=0)).astype(int)
            cv2.rectangle(safe,(eye_min[0]-round(fw*.18),eye_min[1]-round(fh*.13)),
                          (eye_max[0]+round(fw*.18),eye_max[1]+round(fh*.07)),0,-1)
            nx,ny=np.round(points[2]).astype(int)
            cv2.ellipse(safe,(nx,ny),(max(2,round(fw*.10)),max(2,round(fh*.05))),0,0,360,0,-1)
            # Protect the mouth rather than excluding the entire lower face.
            mouth=points[3:5].mean(axis=0)
            cv2.ellipse(safe,tuple(np.round(mouth).astype(int)),
                        (max(3,round(fw*.27)),max(3,round(fh*.10))),0,0,360,0,-1)
            mx,my=np.round(mouth).astype(int)
            cv2.rectangle(safe,(mx-round(fw*.27),my-round(fh*.10)),
                          (mx+round(fw*.27),my+round(fh*.10)),0,-1)
            safe &= (alpha>=250).astype(np.uint8)
            lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
            if (safe>0).sum() < 40:
                continue
            reference=np.median(lab[safe>0],axis=0)
            safe &= ((lab[...,0]>reference[0]-35)&(np.abs(lab[...,1]-reference[1])<24)&
                     (np.abs(lab[...,2]-reference[2])<28)).astype(np.uint8)
            if (safe>0).sum()<40:
                continue
            report["faces"]+=1
            radius=max(2,min(18,round(fw*.014)))
            size=2*radius+5
            light=lab[...,0]
            # Median is used only to find local outliers, never as output skin.
            local_light=cv2.medianBlur(light.astype(np.uint8),size).astype(np.float32)
            local_red=cv2.medianBlur(lab[...,1].astype(np.uint8),size).astype(np.float32)
            dark=(local_light-light)>(5 if spots else 10)
            red=(lab[...,1]-local_red)>5
            candidate=(safe>0)&dark&(red|spots)
            learned=np.zeros(safe.shape,dtype=bool)
            if clean and spots:
                learned=self.spot_detector.predict(rgb)>=.25
            count,labels,stats,_=cv2.connectedComponentsWithStats(candidate.astype(np.uint8),8)
            classical_count=count
            # Keep classical point targets separate: unioning adjacent learned
            # clusters previously swallowed otherwise valid small targets.
            extra=(safe>0)&learned&~candidate
            extra_count,extra_labels,extra_stats,_=cv2.connectedComponentsWithStats(extra.astype(np.uint8),8)
            extra_pixels=extra_labels>0
            labels[extra_pixels]=extra_labels[extra_pixels]+count-1
            stats=np.concatenate([stats,extra_stats[1:]],axis=0)
            count+=extra_count-1
            candidate |= extra
            # Long dark structures are likely hairs/creases, never healing targets.
            protected=np.zeros(safe.shape,dtype=np.uint8)
            lesions=[]
            for label in range(1,count):
                bx,by,bw,bh,area=stats[label]
                if max(bw,bh)/max(1,min(bw,bh))>2.5:
                    protected[labels==label]=1
                    continue
                # Learned clusters can contain several adjacent freckles. The
                # former tiny-component limit silently discarded those clusters.
                limit_radius=radius*3 if label>=classical_count else radius
                if 2<=area<=np.pi*(limit_radius+1)**2 and max(bw,bh)<=2*limit_radius+3:
                    lesions.append((label,int(area)))
            protected=cv2.dilate(protected,np.ones((3,3),np.uint8))>0
            safe[protected]=0
            changed=np.zeros(safe.shape,dtype=bool)
            working=rgb.copy()
            if clean:
                for label,_ in sorted(lesions,key=lambda item:item[1],reverse=True)[:512]:
                    ys,xs=np.where(labels==label)
                    cx,cy=round(xs.mean()),round(ys.mean())
                    patch_radius=max(2,min(round(fw*.08),int(np.ceil(max(np.ptp(xs),np.ptp(ys))/2))+3))
                    x0,y0=cx-patch_radius,cy-patch_radius
                    x1,y1=cx+patch_radius+1,cy+patch_radius+1
                    if x0<0 or y0<0 or x1>fw or y1>fh:
                        continue
                    lesion=cv2.dilate((labels[y0:y1,x0:x1]==label).astype(np.uint8),np.ones((3,3),np.uint8))>0
                    lesion &= safe[y0:y1,x0:x1]>0
                    if not lesion.any():
                        continue
                    ring=~lesion
                    if ring.sum()<4:
                        continue
                    target_tone=np.median(rgb[y0:y1,x0:x1][ring],axis=0)
                    best=None;best_score=float("inf")
                    footprint=cv2.dilate(lesion.astype(np.uint8),np.ones((3,3),np.uint8))>0
                    offsets=[(dy*k,dx*k) for k in (2,3,5,7,10,14) for dy,dx in
                             [(0,1),(0,-1),(1,0),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]]
                    for dy,dx in offsets:
                        sx,sy=x0+dx*patch_radius,y0+dy*patch_radius
                        ex,ey=sx+(x1-x0),sy+(y1-y0)
                        if sx<0 or sy<0 or ex>fw or ey>fh:
                            continue
                        # A freckle elsewhere in a donor patch is irrelevant:
                        # require clean texture only where healing gradients
                        # actually read it, including their one-pixel boundary.
                        if not np.all(safe[sy:ey,sx:ex][footprint]) or candidate[sy:ey,sx:ex][footprint].any():
                            continue
                        donor=rgb[sy:ey,sx:ex]
                        tone=np.median(donor.reshape(-1,3),axis=0)
                        score=float(np.mean((tone-target_tone)**2))
                        if score<best_score:
                            best_score=score;best=(donor,tone)
                    # Poisson healing fixes target boundary illumination, so a
                    # clean donor with a different average tone can still work.
                    if best is None or best_score>256:
                        continue
                    donor,tone=best
                    target_texture=np.std(rgb[y0:y1,x0:x1][ring].astype(float),axis=0)
                    donor_texture=np.std(donor.reshape(-1,3).astype(float),axis=0)
                    if np.max(np.abs(target_texture-donor_texture))>8:
                        continue
                    donor=np.clip(donor.astype(float)+np.clip(target_tone-tone,-6,6),0,255)
                    # Match native illumination at the boundary, transfer the
                    # donor's local texture gradients only inside the small spot.
                    healed=heal_patch(working[y0:y1,x0:x1],donor,lesion)
                    working[y0:y1,x0:x1][lesion]=healed[lesion]
                    changed[y0:y1,x0:x1] |= lesion
                    report["spots"]+=1
            if sharpen:
                # The same protected skin mask applies to BOTH stages.
                # Never restore eyes, brows, lips or nostrils from model output.
                detail_mask=(safe>0)&(alpha>=250)&~protected
                restored=self.deblur.apply(working,detail_mask,strength=strength)
                changed |= np.any(restored!=working,axis=2)
                working=restored
                # Sharpen coherent luminance edges, not freckles/pore noise.
                # Box statistics are a gate only; no averaged skin is output.
                luminance=working.astype(np.float32)@np.array([.2126,.7152,.0722],dtype=np.float32)
                gx=cv2.Sobel(luminance,cv2.CV_32F,1,0,ksize=3)/8
                gy=cv2.Sobel(luminance,cv2.CV_32F,0,1,ksize=3)/8
                xx=cv2.boxFilter(gx*gx,-1,(5,5));yy=cv2.boxFilter(gy*gy,-1,(5,5))
                xy=cv2.boxFilter(gx*gy,-1,(5,5))
                coherence=np.sqrt((xx-yy)**2+4*xy*xy)/(xx+yy+1e-6)
                gradient=np.hypot(gx,gy)
                eligible=(safe>0)&~protected&(coherence>.55)&(gradient>3)&(gradient<40)
                detail=cv2.Laplacian(luminance,cv2.CV_32F,ksize=1)
                adjustment=np.clip(-.22*detail,-6,6)[...,None]*np.clip(strength/70,0,1.4)
                values=working.astype(np.float32)
                # Stay within existing local channel ranges: no bright/dark halo.
                lower=cv2.erode(working,np.ones((3,3),np.uint8)).astype(float)
                upper=cv2.dilate(working,np.ones((3,3),np.uint8)).astype(float)
                sharpened=np.round(np.clip(values+adjustment,lower,upper)).astype(np.uint8)
                working[eligible]=sharpened[eligible]
                changed |= eligible
            output[top:bottom,left:right][changed]=working[changed]
        report["changed_pixels"]=int(np.any(output!=original,axis=2).sum())
        report["message"]=("Yüz bulunamadı; görüntü değişmedi." if not report["faces"] else
                           f"{report['faces']} yüz · {report['spots']} leke alanı · {report['changed_pixels']} piksel değişti" +
                           (" · NAFNet seçici detay" if sharpen else ""))
        result=rgba.copy();result[...,:3]=output
        return Image.fromarray(result),report
