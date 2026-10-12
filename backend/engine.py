"""HR foreground matting followed by ViTMatte-B at original pixel resolution."""
import gc
import logging
import os
from pathlib import Path
import numpy as np
from PIL import Image, ImageChops
from .matting import refine_tiled, automatic_detail_region, structural_guide
from .foreground import recover_foreground
from .polish import polish_alpha
from .model_registry import BIREF_REPO, BIREF_REVISION, STRUCTURE_REPO, STRUCTURE_REVISION, VIT_REPO, VIT_REVISION

logger = logging.getLogger("studio.engine")


class BackgroundEngine:
    def __init__(self, cache: Path):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["U2NET_HOME"] = str(cache)
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("OMP_NUM_THREADS", str(min(os.cpu_count() or 2, 8)))
        self.sessions = {}
        self.models = {}
        self._runtime = None

    def runtime_info(self):
        if self._runtime is None:
            import torch
            forced = os.environ.get("STUDIO_DEVICE", "auto").lower()
            if forced not in {"auto", "cpu", "cuda"}:
                raise RuntimeError("STUDIO_DEVICE must be auto, cpu or cuda")
            cuda = torch.cuda.is_available() and forced != "cpu"
            if forced == "cuda" and not cuda:
                raise RuntimeError("CUDA istendi ancak ekran kartı kullanılamıyor.")
            torch.set_num_threads(min(os.cpu_count() or 2, 8))
            self._runtime = {"device": "cuda" if cuda else "cpu",
                             "engine": torch.cuda.get_device_name(0) if cuda else "CPU",
                             "pipeline": "BiRefNet HR yapı + HR-matting → ViTMatte-B", "resolution": 2048}
        return self._runtime

    @staticmethod
    def _report(report, progress, stage):
        if report:
            report(progress, stage)

    def _activate(self, kind, device):
        import torch
        for name, model in self.models.items():
            if name != kind:
                model.to("cpu")
        if device == "cuda":
            torch.cuda.empty_cache()
        if kind not in self.models:
            from transformers import AutoModelForImageSegmentation, VitMatteForImageMatting
            common = {"cache_dir": str(self.cache / "huggingface")}
            if kind in {"hr", "structure"}:
                repo, revision = (BIREF_REPO, BIREF_REVISION) if kind == "hr" else (STRUCTURE_REPO, STRUCTURE_REVISION)
                model = AutoModelForImageSegmentation.from_pretrained(
                    repo, revision=revision, code_revision=revision,
                    trust_remote_code=True, use_safetensors=True, **common)
            else:
                model = VitMatteForImageMatting.from_pretrained(VIT_REPO, revision=VIT_REVISION, **common)
            self.models[kind] = model.eval()
        dtype = torch.float16 if kind in {"hr", "structure"} and device == "cuda" else torch.float32
        return self.models[kind].to(device=device, dtype=dtype)

    def _hr_alpha(self, image, report, kind="hr"):
        import torch
        from torchvision.transforms import functional as tv
        device = self.runtime_info()["device"]
        self._report(report, 8, "İç boşluk modeli hazırlanıyor" if kind == "structure" else "BiRefNet HR hazırlanıyor · ilk kullanımda model indirilir")
        model = self._activate(kind, device)
        rgb = image.convert("RGB").resize((2048, 2048), Image.Resampling.LANCZOS)
        tensor = tv.normalize(tv.to_tensor(rgb), [.485, .456, .406], [.229, .224, .225]).unsqueeze(0)
        self._report(report, 30, "Kol, el ve saç arkası boşlukları kontrol ediliyor" if kind == "structure" else "2048 pikselde ince ayrıntılar ayrılıyor")
        try:
            with torch.inference_mode():
                prediction = model(tensor.to(device=device, dtype=next(model.parameters()).dtype))[-1].sigmoid()
                alpha = prediction[0, 0].float().cpu().numpy()
        except torch.cuda.OutOfMemoryError:
            logger.warning("GPU exhausted; retrying same HR model/resolution on CPU")
            self._report(report, 30, "Ekran kartı belleği dolu · aynı kalite işlemcide sürdürülüyor")
            model = self._activate(kind, "cpu")
            gc.collect(); torch.cuda.empty_cache()
            with torch.inference_mode():
                alpha = model(tensor.float())[-1].sigmoid()[0, 0].float().cpu().numpy()
        if not np.isfinite(alpha).all():
            raise RuntimeError("HR model returned non-finite alpha")
        self._report(report, 55, "HR kesim hazır · saç ayrıntıları hazırlanıyor")
        return Image.fromarray(np.round(np.clip(alpha, 0, 1)*255).astype(np.uint8)).resize(image.size, Image.Resampling.LANCZOS)

    def refine(self, image: Image.Image, alpha: Image.Image, region: Image.Image | None = None, report=None,
               background_guard: Image.Image | None = None):
        import torch
        from transformers import VitMatteImageProcessor
        if background_guard is None:
            structure = self._hr_alpha(image, None, kind="structure")
            guide, background_guard = structural_guide(alpha, structure)
            if region is None:
                alpha = guide
            else:
                selected = np.asarray(region.convert("L")) > 0
                guarded = (np.asarray(background_guard) > 0) & selected
                background_guard = Image.fromarray(guarded.astype(np.uint8)*255)
        device = self.runtime_info()["device"]
        self._report(report, 58, "ViTMatte-B hazırlanıyor · ilk kullanımda model indirilir")
        model = self._activate("vit", device)
        processor = VitMatteImageProcessor.from_pretrained(
            VIT_REPO, revision=VIT_REVISION, cache_dir=str(self.cache / "huggingface"))

        def predict(patch, trimap):
            inputs = processor(images=patch, trimaps=trimap, return_tensors="pt")
            with torch.inference_mode():
                outputs = model(**{key: value.to(device) for key, value in inputs.items()})
            return outputs.alphas[0, 0, :patch.height, :patch.width].float().cpu().numpy()

        def run_pass(base, selected, callback):
            retry_small = False
            try:
                output = refine_tiled(image, base, predict, region=selected, report=callback,
                                      background_guard=background_guard)
            except torch.cuda.OutOfMemoryError:
                retry_small = True
            if retry_small:
                gc.collect(); torch.cuda.empty_cache()
                output = refine_tiled(image, base, predict, region=selected,
                                      tile_size=512, overlap=128, report=callback, background_guard=background_guard)
            return output

        if region is None:
            first_report = lambda n, stage: self._report(report, 60 + round((n-60)*18/35), stage)
            refined = run_pass(alpha, None, first_report)
            self._report(report, 79, "Kaybolmuş ince teller için kenar bölgesi otomatik seçiliyor")
            selected = automatic_detail_region(refined)
            second_report = lambda n, stage: self._report(report, 80 + round((n-60)*15/35), "Otomatik detay taraması · " + stage)
            refined = run_pass(refined, selected, second_report)
        else:
            refined = run_pass(alpha, region, report)
        self._report(report, 96, "Parmak ve saç kenarlarında ince temizlik yapılıyor")
        refined = polish_alpha(image, refined, background_guard=background_guard, region=region, report=report)
        self._report(report, 97, "Saç kenarlarından eski arka plan rengi temizleniyor")
        result = recover_foreground(image, refined, refine_alpha=True)
        self._report(report, 98, "Doğal şeffaflık korunarak sonuç kaydediliyor")
        return result

    def remove(self, image: Image.Image, model: str, refine: bool, report=None) -> Image.Image:
        background_guard = None
        if model == "fast":
            from rembg import new_session, remove
            self._report(report, 15, "Hızlı model hazırlanıyor")
            if "fast" not in self.sessions:
                self.sessions["fast"] = new_session("u2netp", providers=["CPUExecutionProvider"])
            self._report(report, 40, "Arka plan kaldırılıyor")
            result = remove(image.convert("RGB"), session=self.sessions["fast"], alpha_matting=False).convert("RGBA")
            alpha = result.getchannel("A")
        else:
            hair_report = (lambda n,s: self._report(report,8+round((n-8)*22/47),s)) if refine else report
            alpha = self._hr_alpha(image, hair_report)
            if refine:
                shape_report = lambda n,s: self._report(report,32+round((n-8)*22/47),s)
                structure = self._hr_alpha(image, shape_report, kind="structure")
                alpha, background_guard = structural_guide(alpha, structure)
        if refine:
            return self.refine(image, alpha, report=report, background_guard=background_guard)
        result = image.convert("RGBA")
        result.putalpha(ImageChops.multiply(alpha, image.getchannel("A")))
        return result
