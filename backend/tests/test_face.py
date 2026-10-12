from pathlib import Path
import numpy as np
from PIL import Image
from backend.face import FaceRetoucher


class ControlledFace(FaceRetoucher):
    def __init__(self,cache):
        super().__init__(cache)
        class Identity:
            def apply(self,rgb,eligible,**kwargs):return rgb.copy()
        self.deblur=Identity()
        class NoLearnedSpots:
            def predict(self,rgb):return np.zeros(rgb.shape[:2],dtype=float)
        self.spot_detector=NoLearnedSpots()
        class NoSemanticSkin:
            def predict(self,rgb):return None
        self.skin_mask=NoSemanticSkin()
    def detect(self,rgb):
        return [[20,20,140,160,60,90,120,90,90,125,70,155,110,155,.99]]


def sample():
    rng=np.random.default_rng(7)
    rgb=np.clip(np.array([210,165,140])+rng.integers(-2,3,(210,200,3)),0,255).astype(np.uint8)
    rgb[52:56,88:92]=[190,125,110]
    rgb[42:63,73:75]=[50,38,30]  # Hair strand: excluded by tone/shape protection.
    return Image.fromarray(rgb).convert("RGBA")


def test_face_off_is_byte_identical_without_loading_detector(tmp_path):
    class Forbidden(FaceRetoucher):
        def detect(self,*args):
            raise AssertionError("Disabled face pass must not load the model")
    source=sample();result,report=Forbidden(tmp_path).apply(source)
    assert source.tobytes()==result.tobytes()
    assert report["changed_pixels"]==0


def test_local_spot_healing_preserves_alpha_hair_eyes_and_unselected_image(tmp_path):
    source=sample();result,report=ControlledFace(tmp_path).apply(source,clean=True,spots=True)
    before=np.asarray(source);after=np.asarray(result)
    assert report["faces"]==1
    assert report["spots"]>=1
    assert report["changed_pixels"]>0
    assert np.array_equal(before[...,3],after[...,3])
    assert np.array_equal(before[42:63,73:75],after[42:63,73:75])
    assert np.array_equal(before[75:100,40:140],after[75:100,40:140])
    assert np.array_equal(before[170:],after[170:])
    assert report["changed_pixels"]<100


def test_no_detected_face_is_unchanged(tmp_path):
    class NoFace(FaceRetoucher):
        def detect(self,rgb):return []
    source=sample();result,report=NoFace(tmp_path).apply(source,clean=True,sharpen=True)
    assert source.tobytes()==result.tobytes()
    assert report["faces"]==0


def test_clarity_is_bounded_and_keeps_protected_hair_and_alpha(tmp_path):
    source=sample();result,report=ControlledFace(tmp_path).apply(source,sharpen=True)
    before=np.asarray(source);after=np.asarray(result)
    assert np.abs(after[...,:3].astype(int)-before[...,:3].astype(int)).max()<=8
    # Flat random pore noise should not be amplified by edge sharpening.
    assert np.array_equal(after,before)
    assert report["changed_pixels"] == np.any(after[...,:3]!=before[...,:3],axis=2).sum()
    assert np.array_equal(before[42:63,73:75],after[42:63,73:75])
    assert np.array_equal(before[...,3],after[...,3])
    assert report["spots"]==0


def test_model_cannot_modify_protected_eyes_and_lips_even_at_maximum_strength(tmp_path):
    service=ControlledFace(tmp_path)
    class HostileModel:
        def apply(self,rgb,eligible,**options):
            result=rgb.copy();result[eligible]=255
            return result
    service.deblur=HostileModel()
    source=sample();result,_=service.apply(source,clean=True,sharpen=True,strength=100)
    before=np.asarray(source);after=np.asarray(result)
    assert np.array_equal(before[75:100,40:140],after[75:100,40:140])
    assert np.array_equal(before[150:169,65:115],after[150:169,65:115])
    assert np.array_equal(before[...,3],after[...,3])


def test_clarity_improves_coherent_edge_without_overshoot(tmp_path):
    rgb=np.full((210,200,3),[210,165,140],dtype=np.uint8)
    for x,offset in enumerate([0,2,8,16,20,20,20]):
        rgb[45:72,95+x]=np.array([210,165,140])+offset
    source=Image.fromarray(rgb).convert("RGBA")
    result,_=ControlledFace(tmp_path).apply(source,sharpen=True)
    after=np.asarray(result)[...,:3]
    assert np.any(after[50:67,95:102]!=rgb[50:67,95:102])
    assert np.all(after>=np.array([210,165,140]))
    assert np.all(after<=np.array([230,185,160]))


def test_learned_detector_heals_low_contrast_spot_and_keeps_features(tmp_path):
    rgb=np.full((210,200,3),[210,165,140],dtype=np.uint8)
    rgb[52:56,88:92]-=3  # Below classical detector's luminance threshold.
    source=Image.fromarray(rgb).convert('RGBA')
    service=ControlledFace(tmp_path)
    class Learned:
        def predict(self,roi):
            mask=np.zeros(roi.shape[:2],dtype=float)
            mask[32:36,68:72]=.9
            mask[65:75,35:45]=.9  # Deliberate false positive on an eye.
            mask[130:140,60:70]=.9  # Deliberate false positive on lips.
            return mask
    service.spot_detector=Learned()
    result,report=service.apply(source,clean=True)
    before=np.asarray(source);after=np.asarray(result)
    assert report['spots']>=1
    assert after[53,89,0]>before[53,89,0]
    assert np.array_equal(before[75:100,40:140],after[75:100,40:140])
    assert np.array_equal(before[150:169,65:115],after[150:169,65:115])
    assert np.array_equal(before[...,3],after[...,3])


def test_learned_detector_not_loaded_for_clarity_or_pimple_only(tmp_path):
    service=ControlledFace(tmp_path)
    class Forbidden:
        def predict(self,rgb):raise AssertionError('Unrequested learned model')
    service.spot_detector=Forbidden()
    service.apply(sample(),sharpen=True)
    service.apply(sample(),clean=True,spots=False)


def test_semantic_skin_treats_bridge_spot_but_keeps_eye_centres_and_hair(tmp_path):
    rgb=np.full((210,200,3),[210,165,140],dtype=np.uint8)
    rgb[96:100,88:92]-=7  # Skin between eyes excluded by old rectangle.
    rgb[48:58,75:77]=[30,25,20]
    source=Image.fromarray(rgb).convert('RGBA')
    service=ControlledFace(tmp_path)
    class Skin:
        def predict(self,rgb):return np.ones(rgb.shape[:2],dtype=bool)
    service.skin_mask=Skin()
    result,report=service.apply(source,clean=True,sharpen=True)
    before=np.asarray(source);after=np.asarray(result)
    assert report['spots']>0
    assert after[97,89,0]>before[97,89,0]
    for x,y in [(60,90),(120,90),(90,155)]:
        assert np.array_equal(before[y-5:y+6,x-5:x+6],after[y-5:y+6,x-5:x+6])
    assert np.array_equal(before[48:58,75:77],after[48:58,75:77])
    assert np.array_equal(before[...,3],after[...,3])


def test_semantic_non_skin_pixels_never_change(tmp_path):
    service=ControlledFace(tmp_path)
    class NoSkin:
        def predict(self,rgb):return np.zeros(rgb.shape[:2],dtype=bool)
    service.skin_mask=NoSkin()
    source=sample();result,report=service.apply(source,clean=True,sharpen=True)
    assert source.tobytes()==result.tobytes()
    assert report['changed_pixels']==0


def test_multiscale_small_spot_is_healed_without_single_pixel_pore(tmp_path):
    rgb=np.full((210,200,3),[210,165,140],dtype=np.uint8)
    rgb[52:56,88:92]-=5
    rgb[60,100]-=10
    source=Image.fromarray(rgb).convert('RGBA')
    result,report=ControlledFace(tmp_path).apply(source,clean=True)
    before=np.asarray(source);after=np.asarray(result)
    assert report['spots']>=1
    assert after[53,89,0]>before[53,89,0]
    assert np.array_equal(before[60,100],after[60,100])
