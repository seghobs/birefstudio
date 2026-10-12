import numpy as np
from PIL import Image
from backend.subject_guard import protect_subject


def test_eye_hole_and_recoloured_iris_restored_from_source():
    source=Image.new('RGBA',(160,160),(70,110,60,255))
    pixels=np.array(source);pixels[60:67,60:67]=[150,180,190,60]
    detection=[20,20,110,120,63,63,100,63,80,90,65,120,95,120,.99]
    result=np.array(protect_subject(source,Image.fromarray(pixels),[detection]))
    assert np.array_equal(result[60:67,60:67],np.array(source)[60:67,60:67])


def test_soft_hair_border_and_background_gap_are_not_hardened():
    source=Image.new('RGBA',(60,60),(100,80,60,255))
    output=np.array(source);output[:,:10,3]=70;output[25:35,25:35,3]=0
    output[10:20,20:30]=[105,85,65,253]
    result=np.array(protect_subject(source,Image.fromarray(output)))
    assert np.array_equal(result[:,:10],output[:,:10])
    assert np.array_equal(result[25:35,25:35],output[25:35,25:35])
    assert np.array_equal(result[12:18,22:28],np.array(source)[12:18,22:28])


def test_false_face_on_background_does_not_restore_background():
    source=Image.new('RGBA',(160,160),(70,110,60,255))
    empty=Image.new('RGBA',source.size,(0,0,0,0))
    detection=[20,20,110,120,63,63,100,63,80,90,65,120,95,120,.99]
    assert np.array_equal(np.array(protect_subject(source,empty,[detection])),np.array(empty))
