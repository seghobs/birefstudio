import numpy as np
from backend.healing import heal_patch


def test_healing_removes_flat_blemish_without_boundary_seam():
    source=np.full((15,15,3),180,dtype=np.uint8);source[6:9,6:9]=110
    mask=np.zeros((15,15),bool);mask[5:10,5:10]=True
    result=heal_patch(source,np.full(source.shape,150,dtype=np.uint8),mask)
    assert np.all(result==180)
    assert np.array_equal(result[~mask],source[~mask])


def test_healing_keeps_donor_microtexture_and_unselected_pixels():
    source=np.full((15,15,3),180,dtype=np.uint8)
    donor=np.full(source.shape,160,dtype=np.uint8);donor[6:9:2,6:9:2]=164
    mask=np.zeros((15,15),bool);mask[4:11,4:11]=True
    result=heal_patch(source,donor,mask)
    assert result[6,6,0]>result[6,7,0]
    assert np.array_equal(result[~mask],source[~mask])
