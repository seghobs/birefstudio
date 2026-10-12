"""Run the actual HR + ViTMatte-B pipeline and save intermediate comparison files."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image
from backend.engine import BackgroundEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/hair-validation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(args.image) as source:
        image = source.convert("RGBA")
    engine = BackgroundEngine(Path("data/models"))
    print(json.dumps(engine.runtime_info(), ensure_ascii=True), flush=True)
    report = lambda progress, stage: print(f"{progress}% {stage}", flush=True)
    start = time.monotonic()
    base = engine.remove(image, "quality", False, report=report)
    base.save(args.output / "hr-only.png")
    refined = engine.refine(image, base.getchannel("A"), report=report)
    refined.save(args.output / "hr-vitmatte.png")
    alpha = np.asarray(refined.getchannel("A"))
    assert refined.size == image.size
    assert alpha.min() < 255 and alpha.max() > 0
    assert ((alpha > 0) & (alpha < 255)).any(), "Expected soft transparency at the edge"
    assert np.all(alpha <= np.asarray(image.getchannel("A")))
    change = np.abs(alpha.astype(float) - np.asarray(base.getchannel("A")).astype(float))
    print(f"PASS: HR 2048 + ViTMatte-B, soft alpha, original {image.size}, changed pixels: {(change>0).sum()}, {time.monotonic()-start:.1f}s", flush=True)
    if engine.runtime_info()["device"] == "cuda":
        import torch
        print(f"GPU peak allocated: {torch.cuda.max_memory_allocated()/1024**3:.2f} GiB", flush=True)


if __name__ == "__main__":
    main()
