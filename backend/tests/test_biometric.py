import numpy as np
import pytest
from PIL import Image
from backend.biometric import safe_frame,align_portrait


def test_safe_frame_centres_eyes_and_keeps_hair_and_shoulders_inside():
    eyes=np.array([[100,120],[160,120]],float)
    head=(75,50,185,225);shoulders=(40,235,220,270)
    box,info=safe_frame(eyes,160,head,shoulders,(50,60))
    x0,y0,x1,y1=box
    assert (x1-x0)/(y1-y0)==pytest.approx(50/60)
    assert (eyes[:,1].mean()-y0)/(y1-y0)==pytest.approx(.42)
    assert x0<head[0] and x1>head[2] and y0<head[1] and y1>head[3]
    assert x0<shoulders[0] and x1>shoulders[2] and y1>shoulders[3]


def test_high_zoom_and_offsets_cannot_cut_protected_bounds():
    head=(75,50,185,225);shoulders=(20,235,240,285)
    box,info=safe_frame(np.array([[100,120],[160,120]]),160,head,shoulders,(50,60),3,100,-100)
    assert box[0]<shoulders[0] and box[2]>shoulders[2]
    assert box[1]<head[1] and box[3]>shoulders[3]
    assert info['protection_limited_zoom']


def test_rigid_rotation_levels_eyes_and_does_not_generate_body_pixels():
    image=Image.new('RGBA',(300,400));array=np.array(image)
    array[50:225,90:210]=[100,80,60,255]
    array[225:380,50:250]=[20,50,100,255]
    image=Image.fromarray(array)
    class Parser:
        def labels(self,rgb):return np.ones(rgb.shape[:2],np.uint8)
    face=[90,60,120,160,125,120,175,126,150,160,130,190,170,190,.99]
    result,box,info=align_portrait(image,face,Parser(),(50,60))
    assert info['eye_level_difference_px']<.00001
    assert abs(info['rotation_degrees'])>1
    assert result.mode=='RGBA' and np.asarray(result)[...,3].min()==0
    assert info['face_size_warning']  # Wide shoulders and target cannot both fit.


def test_extreme_tilt_is_not_silently_frontally_reconstructed():
    face=[90,60,120,160,125,100,175,145,150,160,130,190,170,190,.99]
    with pytest.raises(ValueError):align_portrait(Image.new('RGBA',(300,400)),face,None,(50,60))
