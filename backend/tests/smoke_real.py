"""Optional end-to-end check against a running studio and actual ONNX model."""
import argparse
import io
import time
from pathlib import Path

import requests
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", choices=["fast", "quality"], default="fast")
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    with args.image.open("rb") as source:
        response = requests.post(f"{args.url}/api/jobs", files={"file": (args.image.name, source)},
                                 data={"model": args.model}, timeout=60)
    response.raise_for_status()
    job = response.json()
    print(f"Created {job['id']} using {args.model}", flush=True)
    deadline = time.monotonic() + args.timeout
    while job["status"] not in {"done", "failed"}:
        if time.monotonic() > deadline:
            raise RuntimeError("Timed out waiting for model")
        time.sleep(2)
        response = requests.get(f"{args.url}/api/jobs/{job['id']}", timeout=10)
        response.raise_for_status()
        job = response.json()
    if job["status"] == "failed":
        raise RuntimeError(job["error"])
    response = requests.get(f"{args.url}{job['result_url']}", timeout=60)
    response.raise_for_status()
    result = Image.open(io.BytesIO(response.content))
    assert result.mode == "RGBA" and result.size == (job["width"], job["height"])
    assert result.getchannel("A").getextrema()[0] < 255, "Expected background pixels to become transparent"
    output = args.image.parent / f"{args.image.stem}-{args.model}-result.png"
    output.write_bytes(response.content)
    response = requests.get(f"{args.url}/api/jobs/{job['id']}/download", params={"format":"jpg","preset":"portrait"}, timeout=60)
    response.raise_for_status()
    portrait = Image.open(io.BytesIO(response.content))
    assert portrait.mode == "RGB" and portrait.size == (600,800)
    print(f"PASS: real inference, RGBA transparency, original resolution and portrait JPEG. Output: {output}", flush=True)


if __name__ == "__main__":
    main()
