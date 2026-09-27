"""Local native-resolution comparisons. Flags are review suggestions, not approval."""
import json
import threading
import time
import numpy as np
from PIL import Image, ImageFilter

def compare(original,candidate,strict=False):
    source=original.convert('RGBA')
    result=candidate.convert('RGBa').resize(source.size,Image.Resampling.BOX).convert('RGBA')
    a=np.asarray(source,dtype=float);b=np.asarray(result,dtype=float)
    aa=a[:,:,3]/255;ba=b[:,:,3]/255
    union=np.maximum(aa,ba).sum()
    shape=float(np.abs(aa-ba).sum()/max(1,union))
    common=(aa>.8)&(ba>.8)
    color=float(np.abs(a[:,:,:3][common]-b[:,:,:3][common]).mean()) if common.any() else 0
    mask=Image.fromarray(((aa>.5)*255).astype('uint8'))
    boundary=(np.asarray(mask.filter(ImageFilter.MaxFilter(3)))!=np.asarray(mask.filter(ImageFilter.MinFilter(3))))
    edge=float(np.abs(aa-ba)[boundary].mean()) if boundary.any() else shape
    luma=lambda rgb:rgb[:,:,0]*.2126+rgb[:,:,1]*.7152+rgb[:,:,2]*.0722
    darka=(luma(a)<65)&(aa>.5);darkb=(luma(b)<65)&(ba>.5)
    ink=float(np.logical_xor(darka,darkb).sum()/max(1,np.logical_or(darka,darkb).sum()))
    bright=boundary&(aa>.5)&(ba>.2)&(luma(a)<90)
    halo=float(np.maximum(0,luma(b)-luma(a))[bright].mean()) if bright.any() else 0
    limits=(.08,12,.12,.28,18) if strict else (.15,20,.2,.45,30)
    values=(shape,color,edge,ink,halo)
    labels=('Forma desviada','Color desviado','Borde/alpha desviado','Trazo oscuro alterado','Posible halo claro')
    issues=[label for value,limit,label in zip(values,limits,labels) if value>limit]
    if abs(candidate.width*source.height-candidate.height*source.width)>max(source.size):issues.append('Proporciones diferentes')
    return dict(issues=issues,passed=not issues,score=round(max(v/l for v,l in zip(values,limits)),2),
        metrics=dict(shape=round(shape,3),color=round(color,2),edge=round(edge,3),ink=round(ink,3),halo=round(halo,2)),
        strict=strict,checked_at=time.time(),visual_review_required=True)

class AssetAudit:
    def __init__(self,work):
        self.work=work;self.lock=threading.RLock();self.path=work.store/'asset-audit.json'
        self.results=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.progress=dict(running=False,done=0,total=0,errors=0)
    def paths(self,id_):
        self.work.frame(id_)
        return (self.work.draft(id_) if self.work.draft(id_).exists() else self.work.original(id_),self.work.reference(id_))
    def signature(self,id_):
        paths=self.paths(id_)
        return [[str(p),p.stat().st_mtime_ns,p.stat().st_size] if p and p.exists() else None for p in paths]
    def snapshot(self):
        with self.lock:progress=dict(self.progress);records=dict(self.results)
        results={}
        for id_,record in records.items():
            try:current=record.get('signature')==self.signature(id_)
            except (ValueError,KeyError,OSError):current=False
            results[id_]=dict(record,current=current)
        return dict(progress=progress,results=results)
    def start(self,ids,strict):
        with self.lock:
            if self.progress['running']:raise ValueError('Ya hay un análisis en curso.')
            ids=list(dict.fromkeys(ids))
            for id_ in ids:self.work.frame(id_)
            self.progress=dict(running=True,done=0,total=len(ids),errors=0)
            threading.Thread(target=self.run,args=(ids,strict),daemon=True).start()
            return self.snapshot()
    def run(self,ids,strict):
        try:
            for id_ in ids:
                try:
                    signature=self.signature(id_);current,reference=self.paths(id_)
                    if not reference:raise ValueError('Sin original para comparar')
                    with Image.open(reference) as a,Image.open(current) as b:result=compare(a,b,strict)
                    if signature!=self.signature(id_):raise ValueError('El asset cambió durante el análisis; repetí el control')
                    result['signature']=signature
                except Exception as error:
                    result=dict(error=str(error) if isinstance(error,ValueError) else 'No se pudo leer la imagen',checked_at=time.time())
                    with self.lock:self.progress['errors']+=1
                with self.lock:
                    self.results[id_]=result;self.progress['done']+=1
                    if self.progress['done']%25==0:self.persist()
        finally:
            with self.lock:
                self.progress['running']=False;self.persist()
    def persist(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.results),encoding='utf-8');temp.replace(self.path)
