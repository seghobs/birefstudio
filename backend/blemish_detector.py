"""Pinned learned blemish localization, never learned face reconstruction."""
import hashlib
import threading
from pathlib import Path
import numpy as np

REVISION='30f890aab89b787aae93c3f396dbf32714bd950e'
SHA256='c9e1388b19d9334c90db08308c86de208f535920ee381ae8a9cb63484a78351a'
URL=f'https://www.modelscope.cn/api/v1/models/iic/cv_unet_skin_retouching_torch/repo?Revision={REVISION}&FilePath=joint_20210926.pth'


class BlemishDetector:
    def __init__(self,cache:Path):
        self.cache=cache;self.model=None;self.lock=threading.RLock()

    def load(self):
        import torch,requests
        from .vendor.skin.detection_model.detection_unet_in import DetectionUNet
        with self.lock:
            if self.model is not None:return
            path=self.cache/'face'/'skin-local.pth';path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:
                temporary=path.with_suffix('.tmp');digest=hashlib.sha256()
                with requests.get(URL,stream=True,timeout=(10,120)) as response:
                    response.raise_for_status()
                    with temporary.open('wb') as output:
                        for chunk in response.iter_content(1024*1024):
                            output.write(chunk);digest.update(chunk)
                if digest.hexdigest()!=SHA256:raise RuntimeError('Blemish detector checksum mismatch')
                temporary.replace(path)
            state=torch.load(path,map_location='cpu',weights_only=True)
            model=DetectionUNet(3,1,init_weights=False)
            model.load_state_dict(state['detection_net'])
            self.model=model.eval()

    def predict(self,rgb):
        import torch,cv2
        with self.lock:
            self.load()
            # Only detector input is resized; healing uses native source pixels.
            resized=cv2.resize(rgb,(768,768))
            tensor=torch.from_numpy(resized.transpose(2,0,1).copy()).float()[None]/127.5-1
            with torch.inference_mode():probability=self.model(tensor).sigmoid()[0,0].numpy()
            probability=cv2.resize(probability,(rgb.shape[1],rgb.shape[0]))
            if not np.isfinite(probability).all():raise RuntimeError('Invalid blemish probabilities')
            return probability
