"""Recover foreground colour without eroding semi-transparent hair alpha."""
import numpy as np
from PIL import Image


def recover_foreground(image: Image.Image, alpha: Image.Image, refine_alpha: bool = False) -> Image.Image:
    rgba = image.convert("RGBA")
    rgb = np.asarray(rgba)[..., :3]
    source_alpha = np.asarray(rgba)[..., 3]
    matte = np.asarray(alpha.convert("L"))
    if matte.shape != source_alpha.shape:
        raise ValueError("Foreground alpha dimensions must match the source")
    result = rgba.copy()
    # Already transparent source RGB is not an opaque background composite.
    if source_alpha.min() == 255 and np.any((matte > 0) & (matte < 255)):
        from pymatting import estimate_foreground_ml
        source = rgb.astype(np.float32) / 255
        opacity = matte.astype(np.float32)[..., None] / 255
        foreground, background = estimate_foreground_ml(
            source, opacity[..., 0], return_background=True)
        if refine_alpha:
            # Native RGB colour-line projection: resolve fuzzy neural boundary
            # coverage from the compositing equation, without a spatial blur.
            direction = foreground-background
            separation = np.sum(direction*direction, axis=2)
            projected = np.sum((source-background)*direction, axis=2)/np.maximum(separation,1e-8)
            reconstruction = background+projected[...,None]*direction
            eligible = (matte>=8)&(matte<=247)&(separation>.01)&(np.max(np.abs(source-reconstruction),axis=2)<.06)
            base = opacity[...,0]
            projected = np.clip(projected,np.maximum(base*.35,base-.2),np.minimum(1,base+.2))
            matte = matte.copy()
            matte[eligible] = np.round(projected[eligible]*255).astype(np.uint8)
            opacity = matte.astype(np.float32)[...,None]/255
        # Restore the native-pixel compositing residual that the spatial colour
        # solver regularizes away. Do not sharpen, blur, or resample the subject.
        # Bound the correction near transparent pixels to avoid noise explosion.
        residual = source - (opacity * foreground + (1-opacity) * background)
        correction = residual / np.maximum(opacity, 32/255)
        foreground = np.clip(foreground + np.clip(correction, -.15, .15), 0, 1)
        if not np.isfinite(foreground).all():
            raise RuntimeError("Foreground estimation returned non-finite colours")
        recovered = np.round(np.clip(foreground, 0, 1) * 255).astype(np.uint8)
        # Keep opaque pixels byte-identical. The alpha is never thresholded.
        recovered[matte == 255] = rgb[matte == 255]
        result = Image.fromarray(recovered).convert("RGBA")
    result.putalpha(Image.fromarray(np.minimum(matte, source_alpha)))
    return result
