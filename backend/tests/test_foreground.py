import numpy as np
from PIL import Image
from backend.foreground import recover_foreground


def test_foreground_removes_white_spill_without_eroding_hair():
    alpha = np.full((40, 80), 255, dtype=np.uint8)
    alpha[:, 40:60] = 128
    alpha[:, 60:] = 0
    foreground = np.array([40, 20, 10], dtype=float)
    rgb = np.round(foreground * (alpha[..., None]/255) + 255*(1-alpha[..., None]/255)).astype(np.uint8)
    output = recover_foreground(Image.fromarray(rgb).convert("RGBA"), Image.fromarray(alpha))
    pixels = np.asarray(output)
    assert np.array_equal(pixels[..., 3], alpha)
    assert np.array_equal(pixels[:, :40, :3], rgb[:, :40])
    assert pixels[20, 45, :3].mean() < rgb[20, 45].mean() - 40


def test_transparent_source_colours_are_preserved():
    source = Image.new("RGBA", (12,12), (120,80,40,128))
    result = recover_foreground(source, Image.new("L", source.size, 200))
    assert result.getpixel((5,5)) == (120,80,40,128)


def test_native_texture_survives_colour_solver(monkeypatch):
    import pymatting
    # Simulate colour regularization losing a fine alternating source texture.
    rgb=np.full((20,40,3),100,dtype=np.uint8)
    rgb[:,::2]=110
    alpha=np.full((20,40),128,dtype=np.uint8)
    def regularized(image, matte, **kwargs):
        return np.full(image.shape,.4),np.full(image.shape,.4)
    monkeypatch.setattr(pymatting,"estimate_foreground_ml",regularized)
    output=np.asarray(recover_foreground(Image.fromarray(rgb),Image.fromarray(alpha)))
    assert output[:,::2,:3].mean()-output[:,1::2,:3].mean()>=18
    assert np.array_equal(output[:,:,3],alpha)


def test_colour_projection_preserves_opaque_core_and_empty_background():
    alpha=np.zeros((40,80),dtype=np.uint8);alpha[:,:30]=255;alpha[:,30:55]=100
    rgb=np.round(np.array([60,30,15])*(alpha[...,None]/255)+220*(1-alpha[...,None]/255)).astype(np.uint8)
    output=np.asarray(recover_foreground(Image.fromarray(rgb),Image.fromarray(alpha),refine_alpha=True))
    assert np.array_equal(output[:,:30,:3],rgb[:,:30])
    assert np.all(output[:,:30,3]==255) and np.all(output[:,55:,3]==0)
