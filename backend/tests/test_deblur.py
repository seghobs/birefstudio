import numpy as np
from backend.deblur import transfer_detail
from backend.deblur import NaturalDeblur


def test_no_restored_edge_cannot_smooth_source_texture():
    rng=np.random.default_rng(8)
    source=rng.integers(80,160,(40,40,3),dtype=np.uint8)
    restored=np.full(source.shape,120,dtype=np.float32)
    result=transfer_detail(source,restored,np.ones((40,40),bool))
    assert np.array_equal(source,result)


def test_stronger_edge_is_bounded_and_never_touches_unselected_pixels():
    levels=np.array([100]*15+[102,108,116,120]+[120]*21,dtype=np.uint8)
    source=np.broadcast_to(levels[None,:,None],(40,40,3)).copy()
    restored=source.astype(float);restored[:,15]=100;restored[:,16]=105;restored[:,17]=119
    eligible=np.ones((40,40),bool);eligible[:10]=False
    result=transfer_detail(source,restored,eligible)
    assert np.array_equal(result[:10],source[:10])
    assert np.any(result[10:]!=source[10:])
    assert result.min()>=100 and result.max()<=120


def test_small_face_is_padded_for_nafnet_without_resizing(tmp_path):
    class Session:
        def get_inputs(self):
            return [type('Input',(),{'name':'lq'})()]
        def run(self,_,feed):
            tensor=feed['lq']
            assert tensor.shape==(1,3,384,384)
            return [tensor]
    service=NaturalDeblur(tmp_path);service.session=Session()
    source=np.full((80,120,3),140,dtype=np.uint8)
    output=service.apply(source,np.ones(source.shape[:2],bool))
    assert np.array_equal(output,source)


def test_strength_zero_and_flat_skin_remain_exact_even_with_feature_hint():
    source=np.full((40,40,3),120,dtype=np.uint8)
    restored=np.full(source.shape,135,dtype=np.float32)
    features=np.zeros((40,40),dtype=float);features[12:18,12:18]=1
    eligible=np.ones((40,40),bool)
    assert np.array_equal(transfer_detail(source,restored,eligible,0,features),source)
    result=transfer_detail(source,restored,eligible,100,features)
    assert np.array_equal(result,source)
    assert np.array_equal(result[:10],source[:10])
