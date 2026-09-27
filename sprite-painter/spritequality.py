"""Conservative fidelity alarms, never a replacement for visual approval."""
from collections import Counter
from PIL import Image

def palette_description(original):
    colors=Counter((r,g,b) for r,g,b,a in original.convert('RGBA').getdata() if a>=128)
    return ', '.join('#%02x%02x%02x'%rgb for rgb,_ in colors.most_common(16)) or 'transparent'

def assess_fidelity(original,candidate):
    # Compare at native resolution; new anti-aliased edges are allowed. Premultiplied
    # BOX reduction avoids transparent RGB contaminating color measurements.
    source=original.convert('RGBA')
    result=candidate.convert('RGBa').resize(source.size,Image.Resampling.BOX).convert('RGBA')
    a=list(source.getdata()); b=list(result.getdata())
    mask_a=[p[3]>=128 for p in a];mask_b=[p[3]>=128 for p in b]
    union=sum(x or y for x,y in zip(mask_a,mask_b))
    iou=sum(x and y for x,y in zip(mask_a,mask_b))/max(1,union)
    common=[(x,y) for x,y in zip(a,b) if x[3]>=128 and y[3]>=128]
    error=sum(sum(abs(x[i]-y[i]) for i in range(3))/3 for x,y in common)/max(1,len(common))
    # Ink coverage is only a proxy: it flags loss/thickening of dark strokes,
    # but cannot certify line geometry or identify semantic mistakes.
    dark=lambda p: max(p[:3])<65
    ink_a=sum(dark(x) for x,y in common);ink_b=sum(dark(y) for x,y in common)
    ink_ratio=ink_b/max(1,ink_a)
    issues=[]
    if iou<.78: issues.append('silueta o espesor alterado')
    if error>20: issues.append('color o sombreado alterado')
    if ink_a>=max(3,len(common)*.025) and not .60<=ink_ratio<=1.65: issues.append('cobertura del trazo oscuro alterada')
    return dict(passed=not issues,issues=issues,silhouette_iou=round(iou,4),rgb_error=round(error,2),ink_coverage_ratio=round(ink_ratio,3),visual_review_required=True)
