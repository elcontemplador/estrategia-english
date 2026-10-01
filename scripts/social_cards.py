"""Generate editorial sharing cards without modifying article illustrations."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def font(name, size):
    candidates = [Path('C:/Windows/Fonts')/name,
                  Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSerif.ttf' if name.startswith('georgia') else 'DejaVuSans.ttf')]
    path = next((p for p in candidates if p.is_file()), None)
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)


def wrap(draw, text, face, width):
    lines, current = [], ''
    for word in text.split():
        candidate = (current+' '+word).strip()
        if current and draw.textlength(candidate, font=face)>width:
            lines.append(current); current=word
        else:
            current=candidate
    if current: lines.append(current)
    return lines


def article_card(record, output, base):
    image=Image.new('RGB',(1200,630),'#F6F3EF');draw=ImageDraw.Draw(image)
    red,ink,muted='#9D2235','#1E1E20','#545456'
    draw.rectangle((0,0,1200,12),fill=red)
    draw.text((64,34),'estrategIA',font=font('georgia.ttf',48),fill=red)
    draw.text((840,52),'ENGLISH EDITION',font=font('arial.ttf',21),fill=ink)
    draw.line((64,118,1136,118),fill='#CEC6C0',width=2)
    draw.text((64,146),'ISSUE '+record['id']+'  /  '+record['genre_label'].upper(),font=font('arial.ttf',20),fill=red)
    for size in range(54,27,-2):
        face=font('georgia.ttf',size);lines=wrap(draw,record['title'],face,1060)
        if len(lines)*(size+12)<=280 and all(draw.textlength(line,font=face)<=1060 for line in lines): break
    if len(lines)*(size+12)>280 or any(draw.textlength(line,font=face)>1060 for line in lines):
        raise ValueError('Sharing card title cannot be laid out: '+record['id'])
    for index,line in enumerate(lines):draw.text((64,198+index*(size+12)),line,font=face,fill=ink)
    draw.line((64,516,1136,516),fill='#CEC6C0',width=2)
    source_date=record.get('original_date') or ''
    draw.text((64,546),'Originally published in Spanish · '+source_date,font=font('arial.ttf',21),fill=muted)
    draw.text((64,578),'AI, politics and government',font=font('arial.ttf',20),fill=ink)
    path=output/'assets/social'/f"{record['id']}.jpg";path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path,format='JPEG',quality=90,optimize=True,subsampling=0)
    return {'url':base+'assets/social/'+path.name,'width':1200,'height':630,
            'caption':'estrategIA · Issue '+record['id']+' · '+record['title']}
