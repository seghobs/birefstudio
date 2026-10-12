import numpy as np
from PIL import Image
from backend.eye_detail import enhance_eyes


FACE=[20,20,140,160,60,90,120,90,90,125,70,155,110,155,.99]


def test_eye_detail_is_local_bounded_and_preserves_channel_ratios_and_alpha():
    rgb=np.full((210,200,3),[190,140,100],np.uint8)
    for x in range(48,73):
        rgb[86:95,x]=np.array([40,80,100])*(.7+.2*(x%3))
    source=Image.fromarray(rgb).convert('RGBA')
    result,report=enhance_eyes(source,[FACE])
    before=np.asarray(source);after=np.asarray(result)
    assert report['eye_changed_pixels']>0
    assert np.abs(after[...,:3].astype(int)-before[...,:3]).max()<=4
    assert np.array_equal(before[...,3],after[...,3])
    assert np.array_equal(before[:80],after[:80])
    assert np.array_equal(before[100:],after[100:])
    # Common RGB gain keeps colour ratios to within native rounding error.
    a=before[86:95,48:73,:3].astype(float);b=after[86:95,48:73,:3].astype(float)
    ratio=b[...,2]/a[...,2]
    assert np.abs(b-a*ratio[...,None]).max()<=1.1


def test_uniform_or_uncertain_eyes_are_unchanged():
    source=Image.new('RGBA',(210,200),(120,100,80,255))
    for detections in [[],[FACE],[FACE[:-1]+[.7]]]:
        result,report=enhance_eyes(source,detections)
        assert result.tobytes()==source.tobytes()
        assert report['eye_changed_pixels']==0
