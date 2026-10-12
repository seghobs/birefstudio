"""Conservative local colour-consistency refinement after neural matting."""
import logging
import numpy as np
from PIL import Image
from .matting import make_trimap, tile_positions

logger = logging.getLogger("studio.polish")


def polish_alpha(image: Image.Image, alpha: Image.Image, background_guard: Image.Image | None = None,
                 region: Image.Image | None = None, report=None, tile_size=1024, overlap=192) -> Image.Image:
    from pymatting import estimate_alpha_cf
    base = np.asarray(alpha.convert("L"))
    if base.shape != (image.height,image.width):
        raise ValueError("Polish alpha dimensions must match source")
    guard = np.zeros(base.shape,dtype=bool)
    if background_guard is not None:
        guard = np.asarray(background_guard.convert("L")) > 0
        if guard.shape != base.shape:
            raise ValueError("Polish guard dimensions must match alpha")
    trimap = make_trimap(base,radius=2)
    trimap[guard] = 0
    # Never shrink confidently opaque skin/clothes or quantize weak hair away.
    target = (base > 5) & (base < 250) & ~guard
    if region is not None:
        if region.size != alpha.size:
            raise ValueError("Polish region dimensions must match alpha")
        target &= np.asarray(region.convert("L")) > 0
    if not target.any():
        result=base.copy();result[guard]=0
        return Image.fromarray(result)
    h,w=base.shape;values=np.zeros(base.shape,dtype=np.float32);weights=np.zeros(base.shape,dtype=np.float32)
    rgb=image.convert("RGB")
    for top in tile_positions(h,tile_size,overlap):
        for left in tile_positions(w,tile_size,overlap):
            bottom,right=min(h,top+tile_size),min(w,left+tile_size)
            area=np.s_[top:bottom,left:right];guide=trimap[area]
            if not target[area].any() or not (guide==0).any() or not (guide==255).any():
                continue
            patch=np.asarray(rgb.crop((left,top,right,bottom)),dtype=np.float64)/255
            try:
                estimate=estimate_alpha_cf(patch,guide.astype(np.float64)/255,cg_kwargs={"maxiter":1000})
                if not np.isfinite(estimate).all():
                    raise RuntimeError("Non-finite closed-form alpha")
            except (ValueError,RuntimeError) as error:
                logger.warning("Keeping neural alpha for unresolvable colour patch: %s",error)
                continue
            wy=np.hanning(bottom-top+2)[1:-1];wx=np.hanning(right-left+2)[1:-1]
            weight=np.maximum(np.outer(wy,wx),.001).astype(np.float32)
            values[area]+=np.clip(estimate,0,1).astype(np.float32)*weight
            weights[area]+=weight
    result=base.astype(np.float32)/255;valid=target & (weights>0)
    # Retain 20% of the neural estimate to avoid deleting ambiguous fine hair.
    estimate=np.minimum(result[valid],values[valid]/weights[valid])
    # Classical colour models can overestimate alpha on ambiguous patches.
    # Do not amplify those pixels into a new background halo.
    # A one-sided 80% reduction can erase strands even when the neural mask
    # detected them. Limit this auxiliary cleanup to eight alpha levels;
    # background cores remain zero, independently of this detail safeguard.
    result[valid]=np.maximum(result[valid]-8/255,.2*result[valid]+.8*estimate)
    output=np.round(np.clip(result,0,1)*255).astype(np.uint8)
    output[guard]=0
    if report:
        report(96,"Parmak ve saç kenarlarının renk tutarlılığı kontrol edildi")
    return Image.fromarray(output)
