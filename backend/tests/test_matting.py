import numpy as np
import pytest
from PIL import Image
from backend.matting import make_trimap, refine_tiled, tile_positions, automatic_detail_region, structural_guide


def test_structural_guide_keeps_limb_hole_open_and_soft_hair_uncertain():
    hair = np.full((80,100),255,dtype=np.uint8)
    shape = hair.copy()
    shape[25:55,45:55] = 0
    shape[10:15,20:30] = 80
    guide, guard = structural_guide(Image.fromarray(hair),Image.fromarray(shape))
    assert np.asarray(guide)[40,50] == 0
    assert np.asarray(guard)[40,50] == 255
    assert np.asarray(guard)[25,45] == 0
    assert np.asarray(guide)[12,25] == 80
    assert np.asarray(guard)[12,25] == 0


def test_detail_pass_cannot_refill_structural_background_guard():
    image = Image.new("RGB",(80,80))
    alpha = Image.new("L",image.size,128)
    guard = np.zeros((80,80),dtype=np.uint8);guard[30:50,30:50]=255
    def predict(patch,guide):
        assert np.all(np.asarray(guide)[30:50,30:50] == 0)
        return np.ones((80,80),dtype=np.float32)
    output = refine_tiled(image,alpha,predict,region=Image.new("L",image.size,255),
                          background_guard=Image.fromarray(guard))
    assert np.all(np.asarray(output)[30:50,30:50] == 0)
    assert np.asarray(output)[20,20] == 255


def test_entire_guard_skips_prediction_and_clears_old_artifact():
    image=Image.new("RGB",(80,80))
    def predict(*args):
        pytest.fail("Confident background needs no matting inference")
    output=refine_tiled(image,Image.new("L",image.size,128),predict,
                        background_guard=Image.new("L",image.size,255))
    assert output.getextrema() == (0,0)


def test_background_guard_rejects_wrong_dimensions():
    image=Image.new("RGB",(80,80))
    with pytest.raises(ValueError):
        refine_tiled(image,Image.new("L",image.size,128),lambda *args: None,
                     background_guard=Image.new("L",(20,20)))


def test_automatic_detail_region_expands_boundary_without_selecting_opaque_core():
    alpha = np.zeros((200,200), dtype=np.uint8)
    alpha[60:140,60:140] = 255
    region = np.asarray(automatic_detail_region(Image.fromarray(alpha)))
    assert region[100,50] == 255
    assert region[100,100] == 0
    assert region[0,0] == 0


def test_automatic_region_can_recover_missing_soft_strands():
    image = Image.new("RGB", (200,200))
    alpha = np.zeros((200,200), dtype=np.uint8)
    alpha[60:140,60:140] = 255
    recovered = np.asarray(refine_tiled(image,Image.fromarray(alpha),
        lambda patch,guide: np.full((patch.height,patch.width),.3),
        region=automatic_detail_region(Image.fromarray(alpha))))
    assert recovered[100,50] > 0
    assert recovered[100,100] == 255
    assert recovered[0,0] == 0


def test_empty_alpha_has_no_automatic_detail_region():
    assert automatic_detail_region(Image.new("L",(100,100))).getbbox() is None


def test_automatic_region_does_not_reach_distant_background_or_expand_faint_noise():
    alpha = np.zeros((1200,1200), dtype=np.uint8)
    alpha[300:900,400:800] = 255
    alpha[100,100] = 20
    region = np.asarray(automatic_detail_region(Image.fromarray(alpha)))
    assert region[600,395] == 255
    assert region[600,300] == 0
    assert region[100,100] == 0


def test_trimap_includes_soft_hair_and_boundary():
    alpha = np.zeros((80,100), dtype=np.uint8)
    alpha[15:65,30:70] = 255
    alpha[20:25,20:30] = 80
    trimap = make_trimap(alpha, radius=4)
    assert trimap[40,50] == 255
    assert trimap[0,0] == 0
    assert trimap[22,25] == 128
    assert trimap[40,29] == 128
    assert set(np.unique(trimap)) == {0,128,255}


def test_overlapping_tiles_preserve_soft_alpha_without_seams():
    image = Image.new("RGB", (180,150))
    alpha = Image.fromarray(np.full((150,180),128,dtype=np.uint8))
    calls = []
    def predict(patch, trimap):
        calls.append(patch.size)
        return np.full((patch.height,patch.width), .37, dtype=np.float32)
    refined = refine_tiled(image,alpha,predict,tile_size=64,overlap=16)
    assert len(calls) > 1
    assert all(w<=64 and h<=64 for w,h in calls)
    assert np.all(np.asarray(refined)==94)
    assert refined.size == image.size


def test_local_refinement_preserves_unmarked_pixels():
    image = Image.new("RGB",(120,100))
    alpha = Image.fromarray(np.full((100,120),65,dtype=np.uint8))
    region = np.zeros((100,120), dtype=np.uint8)
    region[40:60,50:70]=255
    refined = np.asarray(refine_tiled(image,alpha,lambda patch,guide: np.full((patch.height,patch.width),.8),Image.fromarray(region),tile_size=64,overlap=16))
    assert refined[50,60] == 204
    assert refined[0,0] == 65 and refined[99,119] == 65
    assert 65 < refined[40,50] < 204


def test_fully_known_background_skips_model():
    image = Image.new("RGB",(100,100))
    alpha = Image.new("L",image.size)
    def forbidden(*args):
        pytest.fail("No uncertain region should require model inference")
    assert np.all(np.asarray(refine_tiled(image,alpha,forbidden))==0)


def test_invalid_model_alpha_is_rejected():
    image = Image.new("RGB",(100,100))
    alpha = Image.new("L",image.size,128)
    with pytest.raises(RuntimeError):
        refine_tiled(image,alpha,lambda patch,guide: np.full((100,100),np.nan))


def test_tiles_cover_final_edge():
    assert tile_positions(3000,1024,192)[-1] == 1976
    assert tile_positions(512,1024,192) == [0]
