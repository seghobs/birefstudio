import io,re,zlib
import numpy as np
import pytest
from PIL import Image
from backend.print_sheet import layout,px,portrait_crop,render_sheet,lossless_pdf
from backend.main import create_app
from fastapi.testclient import TestClient
from backend.tests.test_api import FakeEngine,upload


def test_turkish_four_prints_need_larger_paper_and_have_real_dimensions():
    with pytest.raises(ValueError):layout('10x15',50,60,4)
    with pytest.raises(ValueError):layout('10x15',80,20,4)
    plan=layout('13x18',50,60,4)
    assert (plan['columns'],plan['rows'])==(2,2)
    assert len(plan['cells_mm'])==4
    for x,y,w,h in plan['cells_mm']:
        assert w==50 and h==60 and x>=5 and y>=5 and x+w<=125 and y+h<=175


def test_tiles_are_identical_white_and_without_stretch():
    image=Image.new('RGBA',(300,400),(0,0,0,0))
    image.paste((50,100,150,255),(80,50,220,350))
    plan=layout('10x15',35,45,4)
    box=portrait_crop(image,35/45,zoom=1)
    assert (box[2]-box[0])/(box[3]-box[1])==pytest.approx(35/45)
    sheet=render_sheet(image,plan,box,False)
    tiles=[np.asarray(sheet.crop((px(x),px(y),px(x)+px(w),px(y)+px(h)))) for x,y,w,h in plan['cells_mm']]
    assert all(np.array_equal(tiles[0],tile) for tile in tiles)
    assert tuple(tiles[0][0,0])==(255,255,255)
    assert sheet.size==(1181,1772)


def test_pdf_has_exact_paper_size_and_lossless_repeated_tile():
    plan=layout('13x18',50,60,4)
    sheet=render_sheet(Image.new('RGBA',(300,400),(80,110,140,255)),plan,(0,0,300,400))
    pdf=lossless_pdf(sheet,plan)
    assert b'/FlateDecode' in pdf and b'/DCTDecode' not in pdf
    box=re.search(rb'/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]',pdf)
    assert float(box[1])*25.4/72==pytest.approx(130,abs=.0001)
    assert float(box[2])*25.4/72==pytest.approx(180,abs=.0001)
    assert pdf.count(b'/Photo Do')==4
    start=pdf.index(b'stream\n')+7;end=pdf.index(b'\nendstream',start)
    assert len(zlib.decompress(pdf[start:end]))==px(50)*px(60)*3


def test_print_endpoint_validates_fit_and_exports_document_source(tmp_path):
    class Face:
        def apply(self,image,**kwargs):
            return Image.new('RGBA',image.size,(250,0,0,255)),{}
    with TestClient(create_app(tmp_path,FakeEngine(),Face())) as client:
        job=upload(client,face_clean='true')
        url=f"/api/jobs/{job['id']}/print-sheet"
        assert client.get(url,params={'paper':'10x15','auto_face':'false'}).status_code==422
        result=client.get(url,params={'auto_face':'false','marks':'false'})
        assert result.status_code==200
        im=Image.open(io.BytesIO(result.content));assert im.size==(1535,2126)
        assert im.info['dpi'][0]==pytest.approx(300,abs=.01)
        assert im.getpixel((im.width//2-150,im.height//2-150))!=(250,0,0)
        edited=client.get(url,params={'auto_face':'false','marks':'false','source':'edited'})
        edited_image=Image.open(io.BytesIO(edited.content))
        assert edited_image.getpixel((edited_image.width//2-150,edited_image.height//2-150))==(250,0,0)
        assert client.get(url,params={'auto_face':'false','format':'pdf'}).content.startswith(b'%PDF-1.4')
        assert client.get(url,params={'copies':'0'}).status_code==422
        assert client.get(url,params={'zoom':'4'}).status_code==422
