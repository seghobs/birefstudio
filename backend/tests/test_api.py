import io
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.main import create_app, decode_image, Store


class FakeEngine:
    def remove(self, image, model, refine, report=None):
        result = image.copy()
        alpha = Image.new("L", image.size)
        ImageDraw.Draw(alpha).rectangle((10, 10, image.width-10, image.height-10), fill=255)
        result.putalpha(alpha)
        if report:
            report(95, "Test sonucu hazırlanıyor")
        return result

    def refine(self, image, alpha, region=None, report=None):
        result = image.copy()
        result.putalpha(alpha)
        if report:
            report(95, "Bölgesel saç detayı")
        return result


def picture(size=(80, 100), color=(200, 100, 50, 255), format="PNG"):
    image = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    image.save(buf, format=format)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, FakeEngine())) as client:
        yield client


def upload(client, **options):
    response = client.post("/api/jobs", files={"file": ("test.png", picture(), "image/png")}, data=options)
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "failed"}:
            return job
        time.sleep(.02)
    pytest.fail("Job did not finish")


def test_upload_poll_result_and_alpha(client):
    job = upload(client, model="quality", refine="true")
    assert job["status"] == "done" and job["refine"] is True
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]
    image = Image.open(io.BytesIO(client.get(job["result_url"]).content))
    assert image.size == (80, 100)
    assert image.getpixel((0, 0))[3] == 0
    assert image.getpixel((40, 50))[3] == 255
    assert job["progress"] == 100 and job["pipeline"] == "BiRefNet HR-matting + Yapı kontrolü + ViTMatte-B"


def test_detail_brush_creates_new_job_preserving_original(client):
    job = upload(client)
    response = client.post(f"/api/jobs/{job['id']}/refine", files={"file":("mask.png",picture(color=(255,255,255,255)),"image/png")})
    assert response.status_code == 202
    new_id = response.json()["id"]
    assert new_id != job["id"]
    for _ in range(100):
        new_job = client.get(f"/api/jobs/{new_id}").json()
        if new_job["status"] == "done":
            break
        time.sleep(.02)
    assert new_job["status"] == "done"
    assert "Bölgesel" in new_job["pipeline"]
    assert client.get(job["result_url"]).status_code == 200
    assert client.get(f"/api/jobs/{new_id}/original").content == client.get(job["original_url"]).content


def test_detail_brush_rejects_empty_and_wrong_dimensions(client):
    job = upload(client)
    url = f"/api/jobs/{job['id']}/refine"
    assert client.post(url,files={"file":("empty.png",picture(color=(0,0,0,255)),"image/png")}).status_code == 422
    assert client.post(url,files={"file":("wrong.png",picture(size=(10,10)),"image/png")}).status_code == 422
    assert len(client.get("/api/jobs").json()) == 1


def test_fast_default_skips_second_stage(client):
    job = upload(client,model="fast")
    assert job["refine"] is False and job["pipeline"] == "U²-Net"


@pytest.mark.parametrize("format,background,preset,size,mode", [
    ("png", "transparent", "original", (80,100), "RGBA"),
    ("jpg", "transparent", "original", (80,100), "RGB"),
    ("png", "#183d32", "original", (80,100), "RGBA"),
    ("jpg", "#ffffff", "portrait", (600,800), "RGB"),
])
def test_export_formats(client, format, background, preset, size, mode):
    job = upload(client)
    response = client.get(f"/api/jobs/{job['id']}/download", params={"format":format,"background":background,"preset":preset})
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    image = Image.open(io.BytesIO(response.content))
    assert image.size == size and image.mode == mode
    if background == "#183d32":
        assert image.getpixel((0,0)) == (24,61,50,255)


def test_edit_changes_alpha_but_not_rgb(client):
    job = upload(client, model="fast")
    response = client.post(f"/api/jobs/{job['id']}/edit", files={"file": ("edit.png", picture(color=(0,255,0,128)),"image/png")})
    assert response.status_code == 200
    image = Image.open(io.BytesIO(client.get(job["result_url"]).content))
    assert image.getpixel((40,50)) == (200,100,50,128)
    wrong = client.post(f"/api/jobs/{job['id']}/edit", files={"file":("wrong.png", picture(size=(50,50)), "image/png")})
    assert wrong.status_code == 422


def test_quality_edit_reapplies_foreground_colour_recovery(client):
    from backend.foreground import recover_foreground
    job = upload(client, model="quality")
    response = client.post(f"/api/jobs/{job['id']}/edit", files={"file":("edit.png", picture(color=(0,255,0,128)),"image/png")})
    assert response.status_code == 200
    actual = Image.open(io.BytesIO(client.get(job["result_url"]).content))
    expected = recover_foreground(Image.open(io.BytesIO(picture())), Image.new("L", actual.size, 128))
    assert actual.tobytes() == expected.tobytes()


def test_original_colour_png_preserves_source_pixels_and_result_alpha(client):
    import numpy as np
    job = upload(client)
    response = client.get(f"/api/jobs/{job['id']}/download", params={"edge_color":"original"})
    assert response.status_code == 200
    downloaded = np.asarray(Image.open(io.BytesIO(response.content)))
    original = np.asarray(Image.open(io.BytesIO(client.get(job["original_url"]).content)))
    result = np.asarray(Image.open(io.BytesIO(client.get(job["result_url"]).content)))
    assert np.array_equal(downloaded[...,:3], original[...,:3])
    assert np.array_equal(downloaded[...,3], result[...,3])
    assert client.get(f"/api/jobs/{job['id']}/download",params={"edge_color":"invalid"}).status_code == 422


def test_face_toggle_uses_saved_base_and_turns_off_without_accumulation(tmp_path):
    class FaceService:
        def __init__(self):self.calls=0
        def apply(self,image,clean=False,sharpen=False,spots=True,**kwargs):
            self.calls+=1;result=image.copy();result.putpixel((40,50),(100,80,60,result.getpixel((40,50))[3]))
            return result,{"faces":1,"spots":1,"changed_pixels":1,"message":"Test yüz"}
    face=FaceService()
    with TestClient(create_app(tmp_path,FakeEngine(),face)) as client:
        base=upload(client)
        assert base["face_clean"] is False and base["face_sharpen"] is False and face.calls==0
        original=client.get(base["result_url"]).content
        def retouch(jid,**data):
            response=client.post(f"/api/jobs/{jid}/retouch",data=data)
            assert response.status_code==202
            new=response.json()
            for _ in range(100):
                new=client.get(f"/api/jobs/{new['id']}").json()
                if new["status"] in {"done","failed"}:break
                time.sleep(.02)
            assert new["status"]=="done"
            return new
        processed=retouch(base["id"],face_clean="true")
        assert processed["face_clean"] and processed["face_report"]["spots"]==1
        assert client.get(base["result_url"]).content==original
        result=Image.open(io.BytesIO(client.get(processed["result_url"]).content))
        assert result.getpixel((40,50))==(100,80,60,255)
        off=retouch(processed["id"],face_clean="false",face_sharpen="false")
        assert client.get(off["result_url"]).content==original
        assert face.calls==1
        assert client.delete(f"/api/jobs/{processed['id']}").status_code==204
        assert not (tmp_path/f"{processed['id']}.base.png").exists()


def test_face_enabled_on_upload_is_applied_after_cutout(tmp_path):
    class FaceService:
        def apply(self,image,**options):
            assert image.getpixel((0,0))[3]==0
            assert options=={"clean":True,"sharpen":False,"spots":True,"strength":70,"eyes":False}
            return image,{"faces":0,"spots":0,"changed_pixels":0,"message":"Yüz yok"}
    with TestClient(create_app(tmp_path,FakeEngine(),FaceService())) as client:
        job=upload(client,face_clean="true")
        assert job["status"]=="done" and job["face_clean"] is True
        assert (tmp_path/f"{job['id']}.base.png").exists()


def test_zip_and_delete(client):
    job = upload(client)
    response = client.get("/api/export")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [f"studio-{job['id']}.png"]
    assert not list(client.app.state.store.root.glob("export-*.zip"))
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert client.get(job["original_url"]).status_code == 404
    assert client.get("/api/export").status_code == 404


def test_edit_preserves_source_semitransparency(client):
    response = client.post("/api/jobs", files={"file":("alpha.png",picture(color=(200,100,50,128)),"image/png")})
    job_id = response.json()["id"]
    for _ in range(100):
        if client.get(f"/api/jobs/{job_id}").json()["status"] == "done":
            break
        time.sleep(.02)
    for _ in range(2):
        response = client.post(f"/api/jobs/{job_id}/edit", files={"file":("edit.png",picture(color=(0,255,0,128)),"image/png")})
        assert response.status_code == 200
        image = Image.open(io.BytesIO(client.get(f"/api/jobs/{job_id}/result").content))
        assert image.getpixel((40,50))[3] == 128


def test_invalid_images_and_options(client):
    assert client.post("/api/jobs", files={"file":("fake.png", b"not image","image/png")}).status_code == 415
    assert client.post("/api/jobs", files={"file":("a.png",picture(),"image/png")}, data={"model":"bad"}).status_code == 422
    job = upload(client)
    assert client.get(f"/api/jobs/{job['id']}/download", params={"background":"red"}).status_code == 422
    assert client.get("/api/jobs/not-a-valid-id").status_code == 404
    assert client.get("/api/jobs/" + "0"*32).status_code == 404


def test_size_limits(client, monkeypatch):
    import backend.main as module
    monkeypatch.setattr(module,"MAX_BYTES",10)
    assert client.post("/api/jobs", files={"file":("x.png",picture(),"image/png")}).status_code == 413
    monkeypatch.setattr(module,"MAX_BYTES",100000)
    monkeypatch.setattr(module,"MAX_PIXELS",100)
    assert client.post("/api/jobs", files={"file":("x.png",picture(),"image/png")}).status_code == 413


def test_exif_orientation():
    source = Image.new("RGB", (40,60))
    exif = source.getexif(); exif[274] = 6
    buf = io.BytesIO(); source.save(buf, "JPEG", exif=exif)
    assert decode_image(buf.getvalue()).size == (60,40)


def test_restart_recovers_jobs(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO jobs (id,name,status,model,refine,width,height,created_at,error) VALUES (?,?,?,?,?,?,?,?,?)", ("1"*32,"x","processing","fast",0,10,10,"today",None))
    restarted = Store(tmp_path)
    assert restarted.get("1"*32)["status"] == "failed"


def test_face_strength_is_persisted_passed_and_validated(tmp_path):
    class FaceService:
        def apply(self,image,**options):
            assert options["strength"]==85
            return image,{"faces":1,"spots":0,"changed_pixels":0,"message":"Test"}
    with TestClient(create_app(tmp_path,FakeEngine(),FaceService())) as client:
        job=upload(client,face_sharpen="true",face_strength="85")
        assert job["status"]=="done" and job["face_strength"]==85
        assert client.post(f"/api/jobs/{job['id']}/retouch",data={"face_strength":"101"}).status_code==422


def test_eye_toggle_is_independent_persisted_and_off_restores_base(tmp_path):
    class FaceService:
        def apply(self,image,**options):
            assert options['eyes'] is True
            assert options['clean'] is False and options['sharpen'] is False
            result=image.copy();result.putpixel((40,50),(190,95,48,255))
            return result,{'message':'Eye test'}
    with TestClient(create_app(tmp_path,FakeEngine(),FaceService())) as client:
        job=upload(client,eye_sharpen='true')
        assert job['status']=='done' and job['eye_sharpen'] is True
        assert job['face_clean'] is False and job['face_sharpen'] is False
        response=client.post(f"/api/jobs/{job['id']}/retouch",data={'eye_sharpen':'false'})
        new=response.json()
        for _ in range(100):
            new=client.get(f"/api/jobs/{new['id']}").json()
            if new['status'] in {'done','failed'}:break
            time.sleep(.02)
        assert new['status']=='done' and new['eye_sharpen'] is False
        image=Image.open(io.BytesIO(client.get(new['result_url']).content))
        assert image.getpixel((40,50))==(200,100,50,255)


def test_import_store_defers_recovery(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO jobs (id,name,status,model,refine,width,height,created_at,error) VALUES (?,?,?,?,?,?,?,?,?)", ("2"*32,"x","processing","fast",0,10,10,"today",None))
    deferred = Store(tmp_path, recover=False)
    assert deferred.get("2"*32)["status"] == "processing"
    deferred.recover_pending()
    assert deferred.get("2"*32)["status"] == "failed"


def test_inference_failure_is_visible(tmp_path):
    class BrokenEngine:
        def remove(self, *args, **kwargs):
            raise RuntimeError("download failed")
    with TestClient(create_app(tmp_path, BrokenEngine())) as client:
        job = upload(client)
        assert job["status"] == "failed" and job["error"]
        assert client.get(job["original_url"]).status_code == 200
        assert client.get(f"/api/jobs/{job['id']}/result").status_code == 409


def test_queue_limit_and_processing_delete(tmp_path):
    release = threading.Event()
    class SlowEngine(FakeEngine):
        def remove(self, *args, **kwargs):
            release.wait(10)
            return super().remove(*args, **kwargs)
    with TestClient(create_app(tmp_path, SlowEngine())) as client:
        try:
            for _ in range(12):
                response = client.post("/api/jobs", files={"file":("x.png",picture(),"image/png")})
                assert response.status_code == 202
            job_id = response.json()["id"]
            assert client.delete(f"/api/jobs/{job_id}").status_code == 409
            assert client.post("/api/jobs", files={"file":("x.png",picture(),"image/png")}).status_code == 429
        finally:
            release.set()
