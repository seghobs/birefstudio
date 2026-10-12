import numpy as np
import pytest
from PIL import Image
from backend.polish import polish_alpha
from backend.matting import make_trimap


def test_thin_opaque_finger_has_foreground_seed_without_hardening_soft_hair():
    alpha=np.zeros((80,100),dtype=np.uint8)
    alpha[10:70,45:51]=255
    alpha[20:60,35]=90
    guide=make_trimap(alpha,radius=12)
    assert guide[40,48]==255
    assert guide[40,35]==128


def test_colour_polish_cannot_amplify_uncertain_edge_or_touch_opaque_core():
    true=np.zeros((80,100),dtype=np.float64);true[:, :40]=1;true[:,40:55]=.25
    rgb=np.round(np.array([30,80,40])*true[...,None]+255*(1-true[...,None])).astype(np.uint8)
    predicted=np.round(true*255).astype(np.uint8);predicted[:,40:55]=160
    output=np.asarray(polish_alpha(Image.fromarray(rgb),Image.fromarray(predicted)))
    assert np.array_equal(output[:,:40],predicted[:,:40])
    assert output[40,47] <= predicted[40,47]
    assert output[40,47] > 0
    assert np.all(output[:,40:55]>=predicted[:,40:55]-8)
    assert np.array_equal(output[:,60:],predicted[:,60:])


def test_polish_preserves_weak_hair_unmarked_area_and_background_guard():
    alpha=np.full((80,100),128,dtype=np.uint8);alpha[10,10]=3
    selected=np.zeros(alpha.shape,dtype=np.uint8);selected[35:45,45:55]=255
    guard=np.zeros(alpha.shape,dtype=np.uint8);guard[40,50]=255
    result=np.asarray(polish_alpha(Image.new("RGB",(100,80)),Image.fromarray(alpha),
        region=Image.fromarray(selected),background_guard=Image.fromarray(guard)))
    assert result[10,10]==3
    assert result[20,20]==128
    assert result[40,50]==0


def test_polish_keeps_neural_mask_when_patch_has_no_foreground_anchor():
    alpha=Image.new("L",(80,80),128)
    result=polish_alpha(Image.new("RGB",alpha.size),alpha)
    assert result.tobytes()==alpha.tobytes()


def test_polish_rejects_size_mismatch():
    with pytest.raises(ValueError):
        polish_alpha(Image.new("RGB",(80,80)),Image.new("L",(40,40)))
