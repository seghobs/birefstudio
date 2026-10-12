import io
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import uuid
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError

from .engine import BackgroundEngine
from .foreground import recover_foreground
from .face import FaceRetoucher

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
logger = logging.getLogger("studio")


def decode_image(raw: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP", "BMP"}:
                    raise HTTPException(415, "JPG, PNG, WEBP veya BMP yükleyin.")
                if source.width * source.height > MAX_PIXELS:
                    raise HTTPException(413, "Görüntü en fazla 40 megapiksel olabilir.")
                source.load()
                return ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(415, "Dosya geçerli bir görüntü değil.") from None
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, "Görüntü en fazla 40 megapiksel olabilir.") from None


class Store:
    def __init__(self, root: Path, recover=True):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = root / "studio.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                model TEXT NOT NULL, refine INTEGER NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, created_at TEXT NOT NULL, error TEXT)""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            for name, definition in {"progress": "INTEGER NOT NULL DEFAULT 0", "stage": "TEXT NOT NULL DEFAULT 'Bekliyor'", "pipeline": "TEXT NOT NULL DEFAULT ''",
                                     "face_clean":"INTEGER NOT NULL DEFAULT 0", "face_sharpen":"INTEGER NOT NULL DEFAULT 0",
                                     "eye_sharpen":"INTEGER NOT NULL DEFAULT 0", "face_strength":"INTEGER NOT NULL DEFAULT 70", "face_spots":"INTEGER NOT NULL DEFAULT 1", "face_report":"TEXT NOT NULL DEFAULT '{}'"}.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            db.execute("UPDATE jobs SET progress=100, stage='Hazır' WHERE status='done'")
            if recover:
                db.execute("UPDATE jobs SET status='failed', error=? WHERE status IN ('queued','processing')",
                           ("Uygulama kapandığı için işlem tamamlanamadı. Fotoğrafı tekrar yükleyin.",))

    def recover_pending(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='failed', error=? WHERE status IN ('queued','processing')",
                       ("Uygulama kapandığı için işlem tamamlanamadı. Fotoğrafı tekrar yükleyin.",))

    def connect(self):
        return sqlite3.connect(self.db, timeout=20)

    def get(self, job_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        return dict(row)

    def update(self, job_id: str, status: str, error=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?, error=? WHERE id=?", (status, error, job_id))
            if status == "done":
                db.execute("UPDATE jobs SET progress=100, stage='Hazır' WHERE id=?", (job_id,))
            elif status == "failed":
                db.execute("UPDATE jobs SET stage='İşlem tamamlanamadı' WHERE id=?", (job_id,))

    def report(self, job_id: str, progress: int, stage: str):
        with self.connect() as db:
            db.execute("UPDATE jobs SET progress=?, stage=? WHERE id=?", (progress, stage, job_id))

    def add(self, job_id, name, model, refine, width, height, pipeline, face_clean=False, face_sharpen=False, face_spots=True, face_strength=70, eye_sharpen=False):
        with self.connect() as db:
            db.execute("INSERT INTO jobs (id,name,status,model,refine,width,height,created_at,error,pipeline) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (job_id, name, "queued", model, int(refine), width, height, datetime.now(timezone.utc).isoformat(), None, pipeline))
            db.execute("UPDATE jobs SET face_clean=?,face_sharpen=?,face_spots=?,face_strength=?,eye_sharpen=? WHERE id=?",
                       (int(face_clean),int(face_sharpen),int(face_spots),face_strength,int(eye_sharpen),job_id))

    def public(self, row: dict):
        return {**row, "refine": bool(row["refine"]), "face_clean":bool(row["face_clean"]),
                "face_sharpen":bool(row["face_sharpen"]), "face_spots":bool(row["face_spots"]),
                "eye_sharpen":bool(row["eye_sharpen"]), "face_report":json.loads(row["face_report"]),
                "original_url": f"/api/jobs/{row['id']}/original",
                "result_url": f"/api/jobs/{row['id']}/result" if row["status"] == "done" else None}


def create_app(data_dir: Path | None = None, engine=None, face_service=None, recover=True):
    store = Store(data_dir or Path(os.environ.get("STUDIO_DATA_DIR", ROOT / "data")),recover=recover)
    engine = engine or BackgroundEngine(store.root / "models")
    face_service = face_service or FaceRetoucher(store.root / "models")
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="background-removal")
    slots = threading.BoundedSemaphore(12)
    edit_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        if not recover:
            store.recover_pending()
        yield
        worker.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="BiRef Studio API", version="1.0.0", lifespan=lifespan)
    app.state.store = store

    def apply_face(job_id, result):
        row=store.get(job_id)
        if row["face_clean"] or row["face_sharpen"] or row["eye_sharpen"]:
            result.save(store.root / f"{job_id}.base.png",format="PNG")
            store.report(job_id,98,"Yüzde küçük leke ve detay kontrolü yapılıyor")
            result,info=face_service.apply(result,clean=bool(row["face_clean"]),
                                           sharpen=bool(row["face_sharpen"]),spots=bool(row["face_spots"]),strength=row["face_strength"],eyes=bool(row["eye_sharpen"]))
            with store.connect() as db:
                db.execute("UPDATE jobs SET face_report=? WHERE id=?",(json.dumps(info,ensure_ascii=False),job_id))
        return result

    def process(job_id, image, model, refine, alpha=None, region=None, skip_background=False):
        try:
            store.update(job_id, "processing")
            report = lambda progress, stage: store.report(job_id, progress, stage)
            if skip_background:
                result=image.copy()
            elif alpha is None:
                result = engine.remove(image, model, refine, report=report)
            else:
                result = engine.refine(image, alpha, region=region, report=report)
            result=apply_face(job_id,result)
            target = store.root / f"{job_id}.png"
            temp = store.root / f"{job_id}.tmp"
            result.save(temp, format="PNG")
            temp.replace(target)
            store.update(job_id, "done")
        except Exception:
            logger.exception("Background removal failed: %s", job_id)
            store.update(job_id, "failed", "İşlem tamamlanamadı. İlk kullanımda modellerin indirilmesi için internet ve yeterli disk alanı gerekir. Tekrar deneyin; sürerse logs/backend.log kaydını kontrol edin.")
        finally:
            image.close()
            if alpha is not None:
                alpha.close()
            if region is not None:
                region.close()
            slots.release()

    @app.get("/api/health")
    def health():
        runtime = engine.runtime_info() if hasattr(engine, "runtime_info") else {"device": "cpu", "engine": "CPU"}
        return {"status": "ok", **runtime, "models": ["quality", "fast"], "max_upload_mb": 20}

    @app.get("/api/jobs")
    def jobs():
        with store.connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
        return [store.public(dict(row)) for row in rows]

    def enqueue(raw, name, model, refine, face_clean=False, face_sharpen=False, face_spots=True, face_strength=70, eye_sharpen=False):
        image = decode_image(raw)
        if not slots.acquire(blocking=False):
            image.close()
            raise HTTPException(429, "İşlem kuyruğu dolu. Biraz sonra tekrar deneyin.")
        job_id = uuid.uuid4().hex
        try:
            image.save(store.root / f"{job_id}.original.png")
            pipeline = "BiRefNet HR-matting" if model == "quality" else "U²-Net"
            if refine:
                pipeline += " + Yapı kontrolü + ViTMatte-B" if model == "quality" else " + ViTMatte-B"
            if face_clean or face_sharpen or eye_sharpen:
                pipeline += " · Yüz rötuşu"
            store.add(job_id, name, model, refine, image.width, image.height, pipeline,face_clean,face_sharpen,face_spots,face_strength,eye_sharpen)
            worker.submit(process, job_id, image, model, refine)
        except Exception:
            slots.release()
            image.close()
            (store.root / f"{job_id}.original.png").unlink(missing_ok=True)
            raise
        return store.public(store.get(job_id))

    @app.post("/api/jobs", status_code=202)
    async def upload(file: UploadFile = File(...), model: Literal["quality", "fast"] = Form("quality"),
                     refine: bool | None = Form(None), face_clean: bool = Form(False),
                     face_sharpen: bool = Form(False), face_spots: bool = Form(True), face_strength: int = Form(70,ge=0,le=100), eye_sharpen: bool = Form(False)):
        try:
            raw = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Dosya boyutu en fazla 20 MB olabilir.")
        name = (file.filename or "fotoğraf").replace("\\", "/").split("/")[-1][:180]
        return await run_in_threadpool(enqueue, raw, name, model, model == "quality" if refine is None else refine,
                                      face_clean,face_sharpen,face_spots,face_strength,eye_sharpen)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return store.public(store.get(job_id))

    def image_path(job_id, original=False):
        row = store.get(job_id)
        if not original and row["status"] != "done":
            raise HTTPException(409, "Fotoğraf henüz hazır değil.")
        path = store.root / f"{job_id}{'.original' if original else ''}.png"
        if not path.exists():
            raise HTTPException(404, "Görüntü dosyası bulunamadı.")
        return path

    @app.get("/api/jobs/{job_id}/original")
    def original(job_id: str):
        return FileResponse(image_path(job_id, True), media_type="image/png")

    @app.get("/api/jobs/{job_id}/result")
    def result(job_id: str):
        return FileResponse(image_path(job_id), media_type="image/png", headers={"Cache-Control": "no-cache"})

    def save_edit(job_id, raw):
        image = decode_image(raw)
        with edit_lock:
            path = image_path(job_id)
            row = store.get(job_id)
            if image.size != (row["width"], row["height"]):
                image.close()
                raise HTTPException(422, "Düzenlenen görüntünün boyutları orijinalle aynı olmalı.")
            with Image.open(image_path(job_id, True)) as source:
                edited = source.convert("RGBA")
                edited.putalpha(ImageChops.darker(image.getchannel("A"), edited.getchannel("A")))
                if row["refine"]:
                    edited = recover_foreground(source, edited.getchannel("A"))
                edited=apply_face(job_id,edited)
                temp = path.with_suffix(".edit.tmp")
                edited.save(temp, format="PNG")
                temp.replace(path)
        image.close()
        return store.public(row)

    @app.post("/api/jobs/{job_id}/edit")
    async def edit(job_id: str, file: UploadFile = File(...)):
        image_path(job_id)
        try:
            raw = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Düzenlenen görüntü 20 MB sınırını aşıyor.")
        return await run_in_threadpool(save_edit, job_id, raw)

    def enqueue_refinement(job_id, raw):
        region = decode_image(raw).convert("L")
        with edit_lock:
            path = image_path(job_id)
            row = store.get(job_id)
            if region.size != (row["width"], row["height"]):
                region.close()
                raise HTTPException(422, "İşaretleme boyutları fotoğrafla aynı olmalı.")
            if not region.getbbox():
                region.close()
                raise HTTPException(422, "İyileştirmek istediğiniz saç kenarını fırçayla işaretleyin.")
            if not slots.acquire(blocking=False):
                region.close()
                raise HTTPException(429, "İşlem kuyruğu dolu. Biraz sonra tekrar deneyin.")
            new_id = uuid.uuid4().hex
            image = alpha = None
            try:
                with Image.open(image_path(job_id, True)) as source:
                    image = source.convert("RGBA")
                with Image.open(path) as result:
                    alpha = result.getchannel("A")
                shutil.copyfile(image_path(job_id, True), store.root / f"{new_id}.original.png")
                store.add(new_id, row["name"], row["model"], True, row["width"], row["height"], "ViTMatte-B · Bölgesel saç detayı",
                          row["face_clean"],row["face_sharpen"],row["face_spots"],row["face_strength"],row["eye_sharpen"])
                worker.submit(process, new_id, image, row["model"], True, alpha, region)
            except Exception:
                slots.release()
                region.close()
                if image is not None:
                    image.close()
                if alpha is not None:
                    alpha.close()
                (store.root / f"{new_id}.original.png").unlink(missing_ok=True)
                raise
        return store.public(store.get(new_id))

    @app.post("/api/jobs/{job_id}/refine", status_code=202)
    async def refine_job(job_id: str, file: UploadFile = File(...)):
        image_path(job_id)
        try:
            raw = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "İşaretleme dosyası 20 MB sınırını aşıyor.")
        # Save as a new job: the previous cutout remains available for comparison.
        return await run_in_threadpool(enqueue_refinement, job_id, raw)

    def enqueue_retouch(job_id, clean, sharpen, spots, strength, eye_sharpen):
        with edit_lock:
            row=store.get(job_id)
            result_path=image_path(job_id)
            base_path=store.root / f"{job_id}.base.png"
            if not base_path.exists():
                base_path=result_path
            if not slots.acquire(blocking=False):
                raise HTTPException(429,"İşlem kuyruğu dolu. Biraz sonra tekrar deneyin.")
            new_id=uuid.uuid4().hex
            image=None
            try:
                with Image.open(base_path) as base:
                    image=base.convert("RGBA")
                shutil.copyfile(image_path(job_id,True),store.root / f"{new_id}.original.png")
                pipeline=row["pipeline"].split(" · Yüz rötuşu")[0]
                if clean or sharpen or eye_sharpen:
                    pipeline += " · Yüz rötuşu"
                store.add(new_id,row["name"],row["model"],row["refine"],row["width"],row["height"],
                          pipeline,clean,sharpen,spots,strength,eye_sharpen)
                worker.submit(process,new_id,image,row["model"],row["refine"],skip_background=True)
            except Exception:
                slots.release()
                if image is not None:
                    image.close()
                (store.root / f"{new_id}.original.png").unlink(missing_ok=True)
                raise
        return store.public(store.get(new_id))

    @app.post("/api/jobs/{job_id}/retouch",status_code=202)
    async def retouch(job_id: str, face_clean: bool = Form(False), face_sharpen: bool = Form(False),
                      face_spots: bool = Form(True), face_strength: int = Form(70,ge=0,le=100), eye_sharpen: bool = Form(False)):
        return await run_in_threadpool(enqueue_retouch,job_id,face_clean,face_sharpen,face_spots,face_strength,eye_sharpen)

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str, background: str = "transparent", format: Literal["png", "jpg"] = "png",
                 preset: Literal["original", "portrait"] = "original",
                 edge_color: Literal["clean", "original"] = "clean"):
        if background != "transparent" and not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
            raise HTTPException(422, "Geçerli bir arka plan rengi seçin.")
        with Image.open(image_path(job_id)) as source:
            image = source.convert("RGBA")
        if edge_color == "original":
            alpha = image.getchannel("A")
            with Image.open(image_path(job_id, True)) as original:
                image = original.convert("RGBA")
            image.putalpha(alpha)
        if preset == "portrait":
            bbox = image.getchannel("A").getbbox()
            if not bbox:
                raise HTTPException(422, "Fotoğrafta görünür bir nesne bulunamadı.")
            subject = ImageOps.contain(image.crop(bbox), (510, 680), Image.Resampling.LANCZOS)
            image = Image.new("RGBA", (600, 800))
            image.alpha_composite(subject, ((600-subject.width)//2, 800-subject.height))
            if background == "transparent":
                background = "#ffffff"
        if background != "transparent" or format == "jpg":
            bg = Image.new("RGBA", image.size, background if background != "transparent" else "#ffffff")
            image = Image.alpha_composite(bg, image)
        if format == "jpg":
            image = image.convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="JPEG" if format == "jpg" else "PNG", **({"quality": 95} if format == "jpg" else {}))
        filename = f"studio-{job_id[:8]}{'-portrait' if preset == 'portrait' else ''}.{format}"
        return Response(buf.getvalue(), media_type="image/jpeg" if format == "jpg" else "image/png",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete(job_id: str):
        with edit_lock:
            row = store.get(job_id)
            if row["status"] in {"queued", "processing"}:
                raise HTTPException(409, "İşlem sürerken fotoğraf silinemez.")
            with store.connect() as db:
                db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            for suffix in (".png", ".original.png", ".base.png"):
                (store.root / f"{job_id}{suffix}").unlink(missing_ok=True)
        return Response(status_code=204)

    @app.get("/api/export")
    def export():
        with store.connect() as db:
            rows = db.execute("SELECT id FROM jobs WHERE status='done' ORDER BY created_at DESC LIMIT 100").fetchall()
        if not rows:
            raise HTTPException(404, "İndirilecek sonuç yok.")
        export_path = store.root / f"export-{uuid.uuid4().hex}.zip"
        with edit_lock, zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for (job_id,) in rows:
                path = store.root / f"{job_id}.png"
                if path.exists():
                    archive.write(path, f"studio-{job_id}.png")
        return FileResponse(export_path, filename="biref-studio.zip", media_type="application/zip",
                            background=BackgroundTask(export_path.unlink, missing_ok=True))

    return app


app = create_app(recover=False)
