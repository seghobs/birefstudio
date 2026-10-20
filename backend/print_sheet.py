"""Physical-size photo sheets: one crop, repeated without changing its aspect."""
import math
import zlib
from PIL import Image,ImageDraw

PAPERS={'10x15':(100,150),'4x6':(101.6,152.4),'13x18':(130,180),'a4':(210,297)}
PRESETS={'tr':(50,60),'35x45':(35,45),'vesikalik':(45,60),'custom':None}
DPI=300

def px(mm):return round(mm*DPI/25.4)

def layout(paper,photo_width,photo_height,copies,gap=3,margin=5):
    pw,ph=PAPERS[paper]
    columns=int((pw-2*margin+gap)//(photo_width+gap))
    rows=int((ph-2*margin+gap)//(photo_height+gap))
    if columns<1 or rows<1 or copies>columns*rows:
        raise ValueError('Bu kâğıda seçilen adet sığmıyor. Daha büyük kâğıt veya daha az adet seçin.')
    if copies==4 and columns<2:
        raise ValueError('Dörtlü 2 × 2 yerleşim için daha geniş kâğıt seçin.')
    columns=min(columns,2 if copies==4 else copies)
    rows=math.ceil(copies/columns)
    # A four-photo grid is explicitly 2 by 2, never a misleading 1x4 strip.
    if rows*photo_height+(rows-1)*gap>ph-2*margin:
        raise ValueError('Bu yerleşim kâğıda sığmıyor. Daha büyük kâğıt seçin.')
    width=columns*photo_width+(columns-1)*gap
    height=rows*photo_height+(rows-1)*gap
    left,top=(pw-width)/2,(ph-height)/2
    cells=[(left+(i%columns)*(photo_width+gap),top+(i//columns)*(photo_height+gap),photo_width,photo_height) for i in range(copies)]
    return {'paper_mm':[pw,ph],'photo_mm':[photo_width,photo_height],'columns':columns,'rows':rows,'cells_mm':cells,'dpi':DPI}

def portrait_crop(image,aspect,face=None,zoom=1,offset_x=0,offset_y=0):
    w,h=image.size
    if face is not None:
        x,y,fw,fh=face[:4]
        crop_h=fh/.58
        crop_w=crop_h*aspect
        cx=x+fw/2
        cy=y-fh*.28+crop_h/2
    else:
        bbox=image.getchannel('A').getbbox() or (0,0,w,h)
        cx=(bbox[0]+bbox[2])/2;cy=(bbox[1]+bbox[3])/2
        crop_h=min(h,w/aspect);crop_w=crop_h*aspect
    crop_h/=zoom;crop_w/=zoom
    cx+=offset_x/100*crop_w;cy+=offset_y/100*crop_h
    # EXTENT can sample white/transparent outside the original without stretch.
    return (cx-crop_w/2,cy-crop_h/2,cx+crop_w/2,cy+crop_h/2)

def render_sheet(image,plan,box,marks=True):
    pw,ph=plan['paper_mm'];fw,fh=plan['photo_mm']
    white=Image.new('RGBA',image.size,'white');white.alpha_composite(image.convert('RGBA'))
    photo=white.convert('RGB').transform((px(fw),px(fh)),Image.Transform.EXTENT,box,Image.Resampling.BICUBIC,fillcolor='white')
    sheet=Image.new('RGB',(px(pw),px(ph)),'white');draw=ImageDraw.Draw(sheet)
    for x,y,w,h in plan['cells_mm']:
        left,top,right,bottom=px(x),px(y),px(x+w),px(y+h)
        sheet.paste(photo,(left,top))
        if marks:
            for xx in [left,right]:
                for yy in [top,bottom]:
                    sx=-1 if xx==left else 1;sy=-1 if yy==top else 1
                    draw.line((xx+sx*px(.5),yy,xx+sx*px(1.5),yy),fill='#a0a0a0',width=1)
                    draw.line((xx,yy+sy*px(.5),xx,yy+sy*px(1.5)),fill='#a0a0a0',width=1)
    return sheet


def lossless_pdf(sheet,plan,marks=True):
    """Embed one lossless RGB tile, repeated at exact millimetre dimensions."""
    unit=72/25.4
    pw,ph=plan['paper_mm'];fw,fh=plan['photo_mm']
    x,y,_,_=plan['cells_mm'][0]
    photo=sheet.crop((px(x),px(y),px(x)+px(fw),px(y)+px(fh))).convert('RGB')
    stream=zlib.compress(photo.tobytes(),6)
    commands=[]
    for x,y,w,h in plan['cells_mm']:
        commands.append(f'q {w*unit:.6f} 0 0 {h*unit:.6f} {x*unit:.6f} {(ph-y-h)*unit:.6f} cm /Photo Do Q')
        if marks:
            for xx in [x,x+w]:
                for yy in [y,y+h]:
                    sx=-1 if xx==x else 1;sy=-1 if yy==y else 1
                    commands.append(f'0.63 G 0.25 w {(xx+sx*.5)*unit:.6f} {(ph-yy)*unit:.6f} m {(xx+sx*1.5)*unit:.6f} {(ph-yy)*unit:.6f} l S')
                    commands.append(f'{xx*unit:.6f} {(ph-yy-sy*.5)*unit:.6f} m {xx*unit:.6f} {(ph-yy-sy*1.5)*unit:.6f} l S')
    content='\n'.join(commands).encode('ascii')
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw*unit:.6f} {ph*unit:.6f}] /Resources << /XObject << /Photo 4 0 R >> >> /Contents 5 0 R >>'.encode(),
             f'<< /Type /XObject /Subtype /Image /Width {photo.width} /Height {photo.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream',
             f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'\nendstream']
    output=bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for index,obj in enumerate(objects,1):
        offsets.append(len(output));output.extend(f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(output);output.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)
