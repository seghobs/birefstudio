"""Semantic skin eligibility; model pixels are never used as image output."""
import hashlib
import threading
import numpy as np

URL = 'https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx'
SHA256 = '0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f'


class SkinMask:
    def __init__(self, cache):
        self.cache = cache
        self.session = None
        self.lock = threading.RLock()

    def load(self):
        import requests
        import onnxruntime as ort
        with self.lock:
            if self.session is not None:
                return
            path = self.cache / 'face' / 'parsing.onnx'
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
                with requests.get(URL, timeout=(10,120)) as response:
                    response.raise_for_status()
                    if hashlib.sha256(response.content).hexdigest() != SHA256:
                        raise RuntimeError('Skin parsing checksum mismatch')
                    temporary = path.with_suffix('.tmp')
                    temporary.write_bytes(response.content)
                    temporary.replace(path)
            options = ort.SessionOptions()
            options.intra_op_num_threads = 4
            self.session = ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider'])

    def predict(self, rgb):
        import cv2
        with self.lock:
            self.load()
            image = cv2.resize(rgb,(512,512)).astype(np.float32)/255
            image = (image-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
            tensor = image.transpose(2,0,1)[None].copy()
            logits = self.session.run(None,{self.session.get_inputs()[0].name:tensor})[0][0]
            if not np.isfinite(logits).all():
                raise RuntimeError('Invalid skin parsing output')
            exp = np.exp(logits-logits.max(axis=0,keepdims=True))
            probabilities = exp/exp.sum(axis=0,keepdims=True)
            # CelebAMask-HQ: 1=skin, 10=nose. All hair/eye/brow/lip classes
            # are excluded, including uncertain class boundaries.
            eligible = np.isin(logits.argmax(axis=0),[1,10]) & (probabilities.max(axis=0)>.5)
            eligible = cv2.resize(eligible.astype(np.uint8),(rgb.shape[1],rgb.shape[0]),interpolation=cv2.INTER_NEAREST)
            return cv2.erode(eligible,np.ones((3,3),np.uint8))>0
