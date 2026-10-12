"""Full-resolution trimaps and overlapping refinement; keep soft alpha values."""
from collections.abc import Callable
import numpy as np
from PIL import Image
from scipy.ndimage import minimum_filter, maximum_filter, distance_transform_edt


def structural_guide(matte: Image.Image, structure: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Use structural segmentation for gaps, matting in supported foreground.

    Do not fill holes or select only the largest foreground component: spaces
    between limbs and multiple people must remain valid background regions.
    Guard only confidently empty pixels a pixel away from the structural edge.
    The remaining uncertain boundary stays available for soft hair matting.
    """
    hair = np.asarray(matte.convert("L"))
    shape = np.asarray(structure.convert("L"))
    if hair.shape != shape.shape:
        raise ValueError("Structural and matting masks must have equal dimensions")
    guide = np.where(shape >= 224, hair, shape).astype(np.uint8)
    guard = minimum_filter((shape <= 2).astype(np.uint8), size=3,
                           mode="constant", cval=1) > 0
    guide[guard] = 0
    return Image.fromarray(guide), Image.fromarray(guard.astype(np.uint8)*255)


def automatic_detail_region(alpha: Image.Image) -> Image.Image:
    """Select a wider uncertain boundary for the same refinement as a detail brush.

    The region is inferred from the existing subject; it does not detect or invent
    hair. Opaque interior stays a foreground guide for ViTMatte.
    """
    base = np.asarray(alpha.convert("L"))
    # A broad unknown ring can turn nearby foliage into foreground. Limit the
    # search to a narrow boundary and avoid expanding from faint mask noise.
    radius = max(12, min(64, round(max(base.shape) * .008)))
    nearby = maximum_filter((base >= 32).astype(np.uint8), size=2*radius+1, mode="constant") > 0
    return Image.fromarray(((nearby & (base < 250)) * 255).astype(np.uint8))


def make_trimap(alpha: np.ndarray, radius: int | None = None) -> np.ndarray:
    radius = radius if radius is not None else max(4, min(40, round(max(alpha.shape) * .012)))
    size = 2 * radius + 1
    foreground = minimum_filter((alpha >= 250).astype(np.uint8), size=size, mode="constant", cval=0) > 0
    # Thin, confidently opaque fingers/clothing can have no seed after a wide
    # erosion. Keep their medial cores; soft hair is not forced opaque.
    distance = distance_transform_edt(alpha >= 254)
    foreground |= (distance >= 2) & (distance >= maximum_filter(distance, size=3)-1e-6)
    background = minimum_filter((alpha <= 5).astype(np.uint8), size=size, mode="constant", cval=1) > 0
    trimap = np.full(alpha.shape, 128, dtype=np.uint8)
    trimap[background] = 0
    trimap[foreground] = 255
    return trimap


def tile_positions(length: int, size: int, overlap: int) -> list[int]:
    if length <= size:
        return [0]
    positions = list(range(0, length - size + 1, size - overlap))
    if positions[-1] != length - size:
        positions.append(length - size)
    return positions


def refine_tiled(image: Image.Image, alpha: Image.Image, predict: Callable,
                 region: Image.Image | None = None, tile_size: int = 1024, overlap: int = 192,
                 report: Callable | None = None, background_guard: Image.Image | None = None) -> Image.Image:
    """Refine original-resolution unknown pixels, feathering overlapping tiles.

    A supplied region is an interactive unknown-region brush. Outside its narrow
    blend halo the existing alpha is preserved, including semi-transparent pixels.
    """
    base = np.asarray(alpha, dtype=np.uint8)
    trimap = make_trimap(base)
    if region is None:
        target = trimap == 128
        blend = target.astype(np.float32)
    else:
        selected = np.asarray(region.convert("L"), dtype=np.uint8) > 0
        # Blend only inside the selection; never blur the alpha or expand its halo.
        blend = np.minimum(distance_transform_edt(selected) / 2, 1).astype(np.float32)
        target = selected
        trimap[target] = 128
    guarded = None
    if background_guard is not None:
        guarded = np.asarray(background_guard.convert("L")) > 0
        if guarded.shape != base.shape:
            raise ValueError("Background guard dimensions must match alpha")
        trimap[guarded] = 0
        target[guarded] = False
        blend[guarded] = 0
    height, width = base.shape
    tasks = []
    for top in tile_positions(height, tile_size, overlap):
        for left in tile_positions(width, tile_size, overlap):
            bottom, right = min(height, top+tile_size), min(width, left+tile_size)
            if target[top:bottom, left:right].any():
                tasks.append((left, top, right, bottom))
    if not tasks:
        if guarded is None:
            return alpha.copy()
        result = base.copy(); result[guarded] = 0
        return Image.fromarray(result)
    values = np.zeros((height, width), dtype=np.float32)
    weights = np.zeros((height, width), dtype=np.float32)
    rgb = image.convert("RGB")
    for index, (left, top, right, bottom) in enumerate(tasks):
        patch = rgb.crop((left, top, right, bottom))
        guide = Image.fromarray(trimap[top:bottom, left:right])
        predicted = np.asarray(predict(patch, guide), dtype=np.float32)
        if predicted.shape != (bottom-top, right-left) or not np.isfinite(predicted).all():
            raise RuntimeError("Matting model returned invalid alpha values")
        predicted = np.clip(predicted, 0, 1)
        wy = np.hanning(bottom-top + 2)[1:-1]
        wx = np.hanning(right-left + 2)[1:-1]
        weight = np.maximum(np.outer(wy, wx), .001).astype(np.float32)
        values[top:bottom, left:right] += predicted * weight
        weights[top:bottom, left:right] += weight
        if report:
            report(60 + round(35 * (index+1) / len(tasks)), f"Saç kenarları inceleniyor · {index+1}/{len(tasks)}")
    estimate = values / np.maximum(weights, .000001)
    result = base.astype(np.float32) / 255
    result[target] = result[target] * (1-blend[target]) + estimate[target] * blend[target]
    if guarded is not None:
        result[guarded] = 0
    return Image.fromarray(np.round(np.clip(result, 0, 1)*255).astype(np.uint8))
