"""Derive inventory hover art from the current normal art, without regeneration."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

def pairs(work):
    by_name={f['name']:f for f in work.frames.values() if '/objects/' in f['path']}
    result=[]
    for name,normal in by_name.items():
        if not name.startswith('0003_') or not name.endswith('_0000'):continue
        hover=by_name.get(name[:-4]+'0001')
        if not hover or normal['dimensions']!=hover['dimensions']:continue
        paths=[work.root/'extracted/objects'/(n+'.png') for n in (name,hover['name'])]
        if not all(p.exists() for p in paths):continue
        with Image.open(paths[0]) as a,Image.open(paths[1]) as b:
            if a.size!=b.size:continue
            x=np.array(a.convert('RGBA'));y=np.array(b.convert('RGBA'))
            changed=np.any(x!=y,axis=2)
            colors,counts=np.unique(y[changed,:3],axis=0,return_counts=True)
            if len(colors)!=1 or not len(counts):continue
            color=colors[0]
            if not (color[0]>200 and color[1]<100 and color[2]<70):continue
            # Only accept a highlight replacing the extraction's background color.
            if len(np.unique(x[changed],axis=0))!=1:continue
            bg=x[changed][0]
            if not (bg[0]>150 and bg[2]>120 and bg[1]<80):continue
            result.append((normal,hover,tuple(int(c) for c in color),a.size))
    return result

def highlight(image,color,original_size):
    image=image.convert('RGBA')
    radius=max(1,round(image.width/original_size[0]))
    alpha=image.getchannel('A')
    expanded=alpha.filter(ImageFilter.MaxFilter(2*radius+1))
    output=Image.new('RGBA',image.size,(*color,0));output.putalpha(expanded)
    output=Image.alpha_composite(output,image)
    # Fully covered illustration pixels remain byte-for-byte identical.
    return output

def sync(work,source_id):
    import base64,io
    for normal,hover,color,size in pairs(work):
        if normal['id']!=source_id:continue
        source=work.draft(source_id) if work.draft(source_id).exists() else work.original(source_id)
        with Image.open(source) as image:
            if image.convert('RGBA').getchannel('A').getextrema()[0]==255:continue
            result=highlight(image,color,size)
        buffer=io.BytesIO();result.save(buffer,format='PNG');data=buffer.getvalue()
        target=work.draft(hover['id']) if work.draft(hover['id']).exists() else work.original(hover['id'])
        if target.read_bytes()==data:continue
        work.save(dict(id=hover['id'],revision=work.revision(hover['id']),png='data:image/png;base64,'+base64.b64encode(data).decode(),offset=work.metadata(source_id).get('offset',[0,0])),selected_variant=dict(operation='inventory-highlight',model='Borde rojo automático',source_asset_id=source_id))
