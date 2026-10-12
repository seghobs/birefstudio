"""Populate pinned model caches before the first photo, without starting servers."""
import gc
from pathlib import Path
import numpy as np
from .engine import BackgroundEngine
from .face import FaceRetoucher
from .deblur import NaturalDeblur


def main():
    import os
    from transformers import VitMatteImageProcessor
    from .model_registry import VIT_REPO,VIT_REVISION
    cache=Path(os.environ.get('STUDIO_DATA_DIR',str(Path(__file__).resolve().parents[1]/'data')))/'models'
    engine=BackgroundEngine(cache)
    for kind in ('hr','structure','vit'):
        print(f'Model hazirlaniyor: {kind} (ilk indirme zaman alabilir)',flush=True)
        engine._activate(kind,'cpu')
        engine.models.clear();gc.collect()
    VitMatteImageProcessor.from_pretrained(VIT_REPO,revision=VIT_REVISION,cache_dir=str(cache/'huggingface'))
    print('Hizli kesim ve yuz modelleri hazirlaniyor...',flush=True)
    from rembg import new_session
    session=new_session('u2netp',providers=['CPUExecutionProvider']);del session
    FaceRetoucher(cache).detect(np.zeros((64,64,3),np.uint8))
    NaturalDeblur(cache).apply(np.zeros((64,64,3),np.uint8),np.zeros((64,64),bool))
    from .blemish_detector import BlemishDetector
    print('Ogrenilmis benek tespit modeli hazirlaniyor...',flush=True)
    BlemishDetector(cache).load()
    from .skin_mask import SkinMask
    print('Cilt/goz/sac bolgeleme modeli hazirlaniyor...',flush=True)
    SkinMask(cache).load()
    print('Tum model onbellekleri hazir.',flush=True)


if __name__=='__main__':main()
