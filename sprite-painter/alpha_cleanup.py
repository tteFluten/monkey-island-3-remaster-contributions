"""Local, reversible alpha contraction with optional dark-ink protection."""
import math
import numpy as np
from PIL import Image, ImageFilter, ImageOps

def remove_magenta(image):
    """Key exterior magenta and unmix its antialiased fringe without painting black."""
    from PIL import ImageDraw
    pixels=np.array(image.convert('RGBA'),dtype=np.float32)
    rgb=pixels[...,:3];alpha=pixels[...,3]
    magenta=(np.minimum(rgb[...,0],rgb[...,2])-rgb[...,1]>30)&(np.minimum(rgb[...,0],rgb[...,2])>90)
    allowed=magenta|(alpha==0)
    mask=ImageOps.expand(Image.fromarray((allowed*255).astype('uint8')),border=1,fill=255)
    ImageDraw.floodfill(mask,(0,0),128,thresh=0)
    exterior=np.asarray(mask)[1:-1,1:-1]==128
    samples=rgb[exterior&magenta&(alpha>0)].astype('uint8')
    if not len(samples):raise ValueError('No se detectó un fondo magenta conectado al exterior.')
    colors,counts=np.unique(samples,axis=0,return_counts=True)
    matte=colors[counts.argmax()].astype(np.float32)
    core=exterior&((np.max(np.abs(rgb-matte),axis=2)<=28)|(alpha==0))
    # Preserve enclosed colors; only process the exterior key and its narrow fringe.
    near=np.asarray(Image.fromarray((exterior*255).astype('uint8')).filter(ImageFilter.MaxFilter(9)))>0
    fringe=exterior&magenta&~core
    target=rgb.copy();best=np.full(alpha.shape,np.inf)
    h,w=alpha.shape
    for dy in range(-6,7):
        for dx in range(-6,7):
            distance=dx*dx+dy*dy
            if not distance or abs(dx)>=w or abs(dy)>=h:continue
            dst=(slice(max(0,-dy),min(h,h-dy)),slice(max(0,-dx),min(w,w-dx)))
            src=(slice(max(0,dy),min(h,h+dy)),slice(max(0,dx),min(w,w+dx)))
            valid=fringe[dst]&~magenta[src]&(alpha[src]>220)&(distance<best[dst])
            target[dst]=np.where(valid[...,None],rgb[src],target[dst]);best[dst]=np.where(valid,distance,best[dst])
    direction=target-matte
    coverage=np.clip(np.sum((rgb-matte)*direction,axis=2)/np.maximum(np.sum(direction*direction,axis=2),1),0,1)
    fix=fringe&np.isfinite(best)
    pixels[fix,:3]=target[fix];pixels[fix,3]=alpha[fix]*coverage[fix]
    pixels[exterior&magenta&~np.isfinite(best)]=0
    pixels[core]=0
    return Image.fromarray(np.rint(pixels).astype('uint8'),'RGBA')

def tint_edge(image, strength):
    """Recolor only the coverage boundary from nearby opaque ink; never invent black."""
    pixels=np.array(image,dtype=np.float32)
    rgb=pixels[...,:3];alpha=pixels[...,3]
    light=rgb@np.array([.2126,.7152,.0722])
    padded=ImageOps.expand(image.getchannel('A'),border=1,fill=0)
    minimum=np.asarray(padded.filter(ImageFilter.MinFilter(3)),dtype=np.float32)[1:-1,1:-1]
    # One antialiased pixel band, including fractional coverage, never the interior.
    rim=np.clip((alpha-minimum)/255,0,1)*strength
    target=rgb.copy();best=np.full(alpha.shape,np.inf)
    h,w=alpha.shape
    for dy in range(-3,4):
        for dx in range(-3,4):
            distance=dx*dx+dy*dy
            if not distance or distance>9 or abs(dx)>=w or abs(dy)>=h:continue
            dst=(slice(max(0,-dy),min(h,h-dy)),slice(max(0,-dx),min(w,w-dx)))
            src=(slice(max(0,dy),min(h,h+dy)),slice(max(0,dx),min(w,w+dx)))
            valid=(alpha[src]>=220)&(light[src]<=100)&(light[src]<light[dst]-5)&(rim[dst]>0)&(distance<best[dst])
            target[dst]=np.where(valid[...,None],rgb[src],target[dst])
            best[dst]=np.where(valid,distance,best[dst])
    pixels[...,:3]=np.rint(rgb+(target-rgb)*rim[...,None])
    return Image.fromarray(pixels.astype('uint8'),'RGBA')

def seam_mask(reference, size):
    """Conservative straight-cut detection at silhouette extrema in original pixels."""
    a=np.asarray(reference.convert('RGBA'))
    opaque=a[...,3]>127
    light=a[...,:3]@np.array([.2126,.7152,.0722])
    mask=np.zeros(opaque.shape,dtype=np.uint8)
    bbox=reference.getchannel('A').getbbox()
    if not bbox:return Image.fromarray(mask).resize(size,Image.Resampling.NEAREST)
    left,top,right,bottom=bbox
    for horizontal,coordinate,start,end in [(True,top,left,right),(True,bottom-1,left,right),(False,left,top,bottom),(False,right-1,top,bottom)]:
        line=opaque[coordinate,start:end] if horizontal else opaque[start:end,coordinate]
        luminance=light[coordinate,start:end] if horizontal else light[start:end,coordinate]
        edges=np.diff(np.r_[False,line,False].astype(int))
        for lo,hi in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
            # An extended flat edge exposing fill, not an existing dark contour.
            if hi-lo<max(5,math.ceil((end-start)*.2)) or np.mean(luminance[lo:hi]>100)<.35:continue
            if horizontal:mask[coordinate,start+lo:start+hi]=255
            else:mask[start+lo:start+hi,coordinate]=255
    return Image.fromarray(mask).resize(size,Image.Resampling.NEAREST).filter(ImageFilter.MaxFilter(7))

def clean(image, amount=0.5, protect_dark=True, tint_strength=0, reference=None, protect_seams=False):
    if not math.isfinite(amount) or not 0 <= amount <= 3:
        raise ValueError('El recorte debe estar entre 0 y 3 píxeles.')
    result=image.convert('RGBA')
    if not math.isfinite(tint_strength) or not 0<=tint_strength<=1:
        raise ValueError('La intensidad del tinte debe estar entre 0 y 1.')
    if amount==0:
        output=tint_edge(result,tint_strength) if tint_strength else result
        return Image.composite(result,output,seam_mask(reference,result.size)) if protect_seams and reference is not None else output
    alpha=result.getchannel('A')
    def erode(radius):
        if radius==0:return alpha
        padded=ImageOps.expand(alpha,border=radius,fill=0)
        return padded.filter(ImageFilter.MinFilter(radius*2+1)).crop((radius,radius,radius+alpha.width,radius+alpha.height))
    low=math.floor(amount);high=math.ceil(amount)
    contracted=Image.blend(erode(low),erode(high),amount-low) if low!=high else erode(low)
    old=np.asarray(alpha,dtype=np.float32)
    cut=np.minimum(old,np.asarray(contracted,dtype=np.float32))
    if protect_dark:
        rgb=np.asarray(result,dtype=np.float32)[...,:3]
        light=rgb[...,0]*.2126+rgb[...,1]*.7152+rgb[...,2]*.0722
        # Dark outline gets a gentler contraction; bright fringe gets full trim.
        strength=.50+.50*np.clip((light-48)/80,0,1)
        cut=old-(old-cut)*strength
    # Kill stray semi-transparent traces (alpha < 10) and boost mask contrast
    # so faint dust outside the sprite disappears without manual cleanup.
    cut=np.where(cut<10,0,np.clip((cut-10)*(255/245),0,255))
    result.putalpha(Image.fromarray(np.rint(cut).astype('uint8'),'L'))
    output=tint_edge(result,tint_strength) if tint_strength else result
    return Image.composite(image.convert('RGBA'),output,seam_mask(reference,result.size)) if protect_seams and reference is not None else output

def alpha_from_original(image, reference):
    """Apply the original's alpha shape to a 4x asset, upscaled with Lanczos AA."""
    rgba = image.convert('RGBA')
    ref = reference.convert('RGBA')
    ref_alpha = ref.getchannel('A')
    if ref_alpha.getextrema()[0] == 255:
        raise ValueError('El original no tiene transparencia. Quitá primero los colores del fondo.')
    # Upscale the original alpha to match the 4x asset size with antialiased Lanczos
    scaled_alpha = ref_alpha.resize(rgba.size, Image.Resampling.LANCZOS)
    # Clamp to clean binary where original was fully opaque/transparent,
    # keep antialiased edges smooth
    orig_arr = np.asarray(ref_alpha, dtype=np.float32)
    # Build a clean mask: fully opaque interior, AA edges, fully transparent exterior
    scaled_arr = np.asarray(scaled_alpha, dtype=np.float32)
    # Boost contrast slightly so Lanczos ringing doesn't leave faint halos
    scaled_arr = np.clip((scaled_arr - 2) * (255 / 251), 0, 255)
    rgba.putalpha(Image.fromarray(np.rint(scaled_arr).astype('uint8'), 'L'))
    if rgba.getchannel('A').getbbox() is None:
        raise ValueError('El alpha del original eliminaría todo el sprite.')
    return rgba


_PRESET_COLORS={'white-2':(255,255,255),'red-4':(255,59,15),'black-2':(0,0,0)}
def _parse_color(raw,preset=None):
    if raw:
        raw=raw.strip().lstrip('#')
        if len(raw)==6:return tuple(int(raw[i:i+2],16) for i in (0,2,4))
        parts=raw.split(',')
        if len(parts)==3:return tuple(int(x) for x in parts)
    return _PRESET_COLORS.get(preset,(255,255,255))

def run(queue,job):
    folder=queue.folder(job['id'])
    reference=None
    if job.get('protect_seams') or job.get('alpha_original'):
        with Image.open(folder/'alpha-reference.png') as original:reference=original.convert('RGBA')
    with Image.open(folder/'alpha-source.png') as image:
        if job.get('alpha_original'):
            result=alpha_from_original(image,reference)
        elif job.get('outline'):
            color=_parse_color(job.get('outline_color'),job['outline'])
            r=int(job.get('outline_radius',2 if job['outline'] in ('white-2','black-2') else 4))
            result=outline(image,color,r)
        else:
            if job.get('remove_magenta'):image=remove_magenta(image)
            result=clean(image,job['trim_pixels'],job['protect_dark'],job.get('tint_strength',0),reference,job.get('protect_seams',False))
    if result.getchannel('A').getbbox() is None:raise ValueError('El recorte eliminaría todo el sprite. Probá un valor menor.')
    result.save(folder/'candidate.png');result.save(folder/'provider.png')
    job['provider_size']=list(result.size);job['stage']='complete'

def outline(image, color=(255,255,255), radius=2):
    """Photoshop-style solid outside stroke with 1 px antialiased outer edge."""
    rgba=image.convert('RGBA')
    orig=np.array(rgba,dtype=np.float32);alpha=orig[...,3];h,w=alpha.shape
    if alpha.min()==255:raise ValueError('El asset necesita transparencia para generar un contorno. Quitá primero el fondo.')
    # Expand from any visible pixel (alpha>0) to avoid gap at antialiased edges.
    binary=np.where(alpha>0,np.uint8(255),np.uint8(0))
    padded=np.pad(binary,radius);expanded=binary.copy()
    for dy in range(-radius,radius+1):
        for dx in range(-radius,radius+1):
            if dx*dx+dy*dy<=radius*radius:
                expanded=np.maximum(expanded,padded[radius+dy:radius+dy+h,radius+dx:radius+dx+w])
    # Solid inside, 1 px AA fringe outside.
    smooth=np.asarray(Image.fromarray(expanded).filter(ImageFilter.GaussianBlur(1.0)),dtype=np.float32)
    stroke_alpha=np.where(expanded>0,255.0,np.clip(smooth,0,255))
    # Composite: stroke behind, original on top.
    stroke=np.zeros_like(orig)
    stroke[...,0]=color[0];stroke[...,1]=color[1];stroke[...,2]=color[2]
    stroke[...,3]=stroke_alpha
    # Standard alpha-over: src=original, dst=stroke
    sa=alpha/255.0;da=stroke_alpha/255.0
    oa=sa+da*(1-sa);oa_safe=np.where(oa>0,oa,1)
    out=np.zeros_like(orig)
    out[...,:3]=(orig[...,:3]*sa[...,None]+stroke[...,:3]*da[...,None]*(1-sa[...,None]))/oa_safe[...,None]
    out[...,3]=oa*255
    return Image.fromarray(np.rint(np.clip(out,0,255)).astype('uint8'),'RGBA')
