"""Simplify sampled silhouettes before scaling, without expanding their bounds."""
from PIL import Image, ImageDraw, ImageFilter
import math

def simplify(points, epsilon):
    if len(points)<3: return points
    keep={0,len(points)-1};stack=[(0,len(points)-1)]
    while stack:
        start,end=stack.pop();a,b=points[start],points[end]
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        distances=[abs(dy*(p[0]-a[0])-dx*(p[1]-a[1]))/length if length else math.dist(p,a) for p in points[start+1:end]]
        if distances and max(distances)>epsilon:
            index=start+1+distances.index(max(distances));keep.add(index);stack.extend([(start,index),(index,end)])
    return [points[i] for i in sorted(keep)]

def smooth_mask(original, size):
    alpha=original.getchannel('A');bounds=alpha.getbbox()
    if not bounds: return Image.new('L',size)
    values=alpha.getcolors(256)
    # Preserve genuinely soft effects rather than polygonizing them.
    if not values or len(values)>16 or original.width*original.height>250000:
        return alpha.resize(size,Image.Resampling.BICUBIC)
    maximum=alpha.getextrema()[1];threshold=max(1,maximum//2)
    solid=set((x,y) for y in range(alpha.height) for x in range(alpha.width) if alpha.getpixel((x,y))>=threshold)
    edges={}
    for x,y in solid:
        for neighbor,a,b in [((x,y-1),(x,y),(x+1,y)),((x+1,y),(x+1,y),(x+1,y+1)),((x,y+1),(x+1,y+1),(x,y+1)),((x-1,y),(x,y+1),(x,y))]:
            if neighbor not in solid: edges.setdefault(a,[]).append(b)
    loops=[]
    while edges:
        start=next(iter(edges));current=start;previous=(start[0]-1,start[1]);points=[start]
        while current in edges:
            candidates=edges[current];dx,dy=current[0]-previous[0],current[1]-previous[1]
            # Follow the rightmost turn where diagonal components touch.
            def turn(p):
                ex,ey=p[0]-current[0],p[1]-current[1]
                cross=dx*ey-dy*ex;dot=dx*ex+dy*ey
                return 0 if cross>0 else 1 if dot>0 else 2 if cross<0 else 3
            nxt=min(candidates,key=turn);candidates.remove(nxt)
            if not candidates: del edges[current]
            previous,current=current,nxt;points.append(current)
            if current==start: break
        if len(points)<4: continue
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]))
        split=max(range(len(points)-1),key=lambda i:math.dist(points[i],points[0]))
        epsilon=1.1 if original.width/original.height>2 and max(original.size)<64 else .65
        poly=simplify(points[:split+1],epsilon)[:-1]+simplify(points[split:],epsilon)[:-1]
        if len(poly)>=3: loops.append((area,poly))
    scale=4 if max(size)<=2048 else 1
    mask=Image.new('L',(size[0]*scale,size[1]*scale));draw=ImageDraw.Draw(mask)
    sx,sy=mask.width/original.width,mask.height/original.height
    for area,poly in sorted(loops,key=lambda item:abs(item[0]),reverse=True):
        draw.polygon([(x*sx,y*sy) for x,y in poly],fill=maximum if area>0 else 0)
    mask=mask.resize(size,Image.Resampling.LANCZOS)
    # Antialiasing may create a halo: clip to the original bounding rectangle.
    clip=Image.new('L',size);box=(math.floor(bounds[0]*size[0]/alpha.width),math.floor(bounds[1]*size[1]/alpha.height),math.ceil(bounds[2]*size[0]/alpha.width),math.ceil(bounds[3]*size[1]/alpha.height))
    clip.paste(mask.crop(box),box)
    return clip

def clean_base(original,size):
    # Interpolate colors to suppress square texels; keep alpha independently fitted.
    up=original.resize(size,Image.Resampling.BICUBIC)
    radius=min(size[0]/original.width,size[1]/original.height)*.35
    up=up.filter(ImageFilter.GaussianBlur(radius))
    up.putalpha(smooth_mask(original,size))
    return up
