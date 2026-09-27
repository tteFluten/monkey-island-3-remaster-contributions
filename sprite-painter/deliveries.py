"""Reviewed, immutable scene deliveries, isolated from the working tree/index."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import threading
import time
from collections import Counter, defaultdict
from PIL import Image
from asset_audit import compare

def digest(data):return hashlib.sha256(data).hexdigest()
def safe_path(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not name.startswith('assets/'):
        raise ValueError('Ruta de entrega inválida.')
    return p
def git(root,*args,data=None,env=None):
    result=subprocess.run(['git','-C',str(root),*args],input=data,capture_output=True,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Git no pudo completar '+args[0]+'. Revisá identidad, permisos y acceso al remoto.')
    return result.stdout
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

class Deliveries:
    def __init__(self,work,lab):
        self.work=work;self.lab=lab;self.root=work.store/'deliveries';self.lock=threading.RLock()
        self.progress=dict(running=False,done=0,total=0);self.report=None
        latest=self.root/'latest.json'
        if latest.exists():self.report=json.loads(latest.read_text(encoding='utf-8'))
    def persist(self):
        self.root.mkdir(parents=True,exist_ok=True)
        tmp=self.root/'latest.tmp';tmp.write_bytes(encode(self.report));tmp.replace(self.root/'latest.json')
    def snapshot(self):
        with self.lock:return dict(progress=dict(self.progress),report=copy.deepcopy(self.report))
    def selected(self,manifest,scope):
        plan=json.loads((self.work.root/'assets/metadata/topaz-scene-plan.json').read_text(encoding='utf-8'))
        rooms=['room-0009'] if scope=='interior' else ['room-0009','room-0010','room-0011']
        scenes=[s for s in plan['scenes'] if s['id'] in rooms]
        if len(scenes)!=len(rooms):raise ValueError('Falta el plan de una escena.')
        sources={s['source'] for scene in scenes for s in scene['sources']}
        rows=[r for r in manifest['files'] if r.get('canonical') and (r.get('source_id') in sources or (scope=='complete' and r['path'].startswith('assets/masters/') and '/objects/0003_' in r['path']) or r.get('asset_id') in ['background-room-'+str(int(x[-4:])) for x in rooms])]
        found={r.get('source_id') for r in rows}
        missing=sorted(sources-found)
        return rows,missing
    def start(self,scope='complete'):
        if scope not in ('complete','interior'):raise ValueError('Alcance desconocido.')
        with self.lock:
            if self.progress['running']:raise ValueError('Ya se está preparando una entrega.')
            self.progress=dict(running=True,done=0,total=0)
            threading.Thread(target=self.analyze,args=(scope,),daemon=True).start()
        return self.snapshot()
    def analyze(self,scope):
        try:
            previous={i['id']:i for i in (self.report or {}).get('items',[])}
            w=self.work;manifest=json.loads((w.root/'assets/manifest.json').read_text(encoding='utf-8'))
            rows,missing=self.selected(manifest,scope)
            report=dict(id=secrets.token_hex(12),scope=scope,created_at=time.time(),status='checking',items=[],missing_sources=missing,base_commit=git(w.root,'rev-parse','origin/main^{commit}').decode().strip(),source_commit=git(w.root,'rev-parse','HEAD').decode().strip())
            with self.lock:self.report=report;self.progress['total']=len(rows)
            approvals=self.lab.approvals();index={r['path']:r for r in manifest['files']}
            folder=self.root/report['id'];folder.mkdir(parents=True,exist_ok=True)
            for row in rows:
                path=row['path'];safe_path(path);id_=digest(path.encode())[:24]
                item=dict(id=id_,name=Path(path).stem,path=path,issues=[],approved=False)
                try:
                    # Register missing scene dependencies so the report can open them for review.
                    if id_ not in w.frames:w.register(w.root/path,'Entrega · dependencias del barco',dimensions=[row['image']['width'],row['image']['height']])
                    with w.lock:
                        source=w.draft(id_) if w.draft(id_).exists() else w.original(id_)
                        data=source.read_bytes();checksum=digest(data);item['sha256']=checksum
                        item['revision']=w.revision(id_)
                    with Image.open(io.BytesIO(data)) as image:
                        image.load();item['dimensions']=list(image.size)
                        if list(image.size)!=[row['image']['width'],row['image']['height']]:item['issues'].append('Dimensiones diferentes')
                        if image.convert('RGBA').getchannel('A').getbbox() is None:item['issues'].append('Imagen vacía')
                        ref=w.reference(id_)
                        if ref:
                            refdata=ref.read_bytes();item['reference_sha256']=digest(refdata)
                            cached=previous.get(id_,{})
                            if cached.get('sha256')==checksum and cached.get('reference_sha256')==item['reference_sha256'] and cached.get('audit',{}).get('strict'):
                                audit=copy.deepcopy(cached['audit'])
                            else:
                                with Image.open(io.BytesIO(refdata)) as original:audit=compare(original,image,strict=True)
                            item['audit']=audit;item['issues']+=audit['issues']
                        else:item['issues'].append('Sin original asociado para control visual')
                    approval=approvals.get(id_)
                    saved=w.frame(id_).get('review',{})
                    item['approved']=bool((approval and approval.get('sha256')==checksum) or (saved.get('state')=='accepted' and saved.get('sha256')==checksum))
                    if not item['approved']:item['issues'].append('Aprobación pendiente o desactualizada')
                    derived=[r for r in manifest['files'] if r.get('derived_from')==path]
                    prepared={path:data}
                    for r in derived:
                        if r.get('transform',{}).get('kind')=='copy':prepared[r['path']]=data
                        elif r.get('transform',{}).get('source_sha256')==checksum:
                            existing=(w.root/safe_path(r['path'])).read_bytes()
                            if digest(existing)!=r['sha256']:raise ValueError('El derivado del fondo no coincide con el manifiesto')
                            prepared[r['path']]=existing
                        else:item['issues'].append('Derivado requiere transformación específica')
                    if not derived and not row.get('asset_id','').startswith('background-room-'):item['issues'].append('Sin copia de runtime asociada')
                    item['targets']=[path]+[r['path'] for r in derived]
                    if not any(issue in item['issues'] for issue in ('Dimensiones diferentes','Derivado requiere transformación específica','Sin copia de runtime asociada')):
                        for target in item['targets']:
                            safe_path(target);dest=folder/'files'/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(prepared[target])
                        item['records']=[copy.deepcopy(index[p]) for p in item['targets']]
                        item['file_hashes']={p:digest(prepared[p]) for p in item['targets']}
                except Exception as error:item['issues'].append(str(error) if isinstance(error,ValueError) else 'No se pudo leer o preparar el asset')
                with self.lock:report['items'].append(item);self.progress['done']+=1
            with self.lock:
                report['ready']=sum(not i['issues'] for i in report['items']);report['blocked']=len(report['items'])-report['ready']+len(missing)
                report['status']='ready' if not report['blocked'] and report['items'] else 'blocked'
                self.persist();(folder/'report.json').write_bytes(encode(report))
        except Exception as error:
            with self.lock:self.report=dict(status='failed',error=str(error) if isinstance(error,ValueError) else 'No se pudo preparar la entrega.');self.persist()
        finally:
            with self.lock:self.progress['running']=False
    def branch(self,id_,name=None,draft=False):
        with self.lock:
            report=copy.deepcopy(self.report)
            if self.progress['running'] or not report or report.get('id')!=id_ or report.get('status') not in ('ready','blocked'):raise ValueError('Primero terminá el análisis de la entrega.')
            if report['status']!='ready' and not draft:raise ValueError('La entrega tiene pendientes. Podés crear un borrador explícito o resolverlos y analizar de nuevo.')
            if report.get('missing_sources') or any(not i.get('records') for i in report['items']):raise ValueError('Faltan archivos o derivados exportables. Revisá el informe antes de crear la rama.')
            if report.get('branch'):return report
            w=self.work;folder=self.root/id_;approvals=self.lab.approvals()
            # Revalidate live image/approval state before publishing the captured snapshot.
            for item in report['items']:
                source=w.draft(item['id']) if w.draft(item['id']).exists() else w.original(item['id'])
                if digest(source.read_bytes())!=item['sha256']:raise ValueError('Un asset cambió desde el análisis. Prepará de nuevo.')
                saved=w.frame(item['id']).get('review',{})
                if not draft and approvals.get(item['id'],{}).get('sha256')!=item['sha256'] and not (saved.get('state')=='accepted' and saved.get('sha256')==item['sha256']):raise ValueError('Cambió una aprobación. Prepará de nuevo.')
                ref=w.reference(item['id'])
                if (digest(ref.read_bytes()) if ref else None)!=item.get('reference_sha256'):raise ValueError('Cambió un original. Prepará de nuevo.')
            base=report['base_commit'];manifest=json.loads(git(w.root,'show',base+':assets/manifest.json'))
            index={r['path']:r for r in manifest['files']};payload={}
            for item in report['items']:
                for record in item['records']:
                    record=copy.deepcopy(record);name=record['path'];data=(folder/'files'/name).read_bytes()
                    if digest(data)!=item.get('file_hashes',{}).get(name,item['sha256']):raise ValueError('La copia de entrega cambió.')
                    record.update(sha256=digest(data),bytes=len(data),review_status='accepted' if not item['issues'] else 'review-pending')
                    if record.get('derived_from'):record['transform']['source_sha256']=item['sha256']
                    index[name]=record;payload[name]=data
            manifest['files']=list(index.values());categories=defaultdict(lambda:dict(files=0,bytes=0));unique={}
            for row in index.values():categories[row['category']]['files']+=1;categories[row['category']]['bytes']+=row['bytes'];unique[row['sha256']]=row['bytes']
            manifest.update(categories=dict(categories),logical_bytes=sum(r['bytes'] for r in index.values()),unique_bytes=sum(unique.values()))
            payload['assets/manifest.json']=encode(manifest)
            report['delivery_state']='draft' if report['blocked'] else 'reviewed'
            public={k:v for k,v in report.items() if k!='items'};public['items']=[{k:v for k,v in i.items() if k!='records'} for i in report['items']]
            payload['assets/metadata/deliveries/barco-'+id_+'.json']=encode(public)
            summary=['# Entrega del barco','', 'Estado: '+report['delivery_state'], '', 'Base: '+base, '', 'Incluye '+str(len(report['items']))+' assets y sus copias de runtime. Se exportaron las versiones en uso del refinador.', '', 'Las animaciones de agua requieren revisión visual y de movimiento antes de considerar esta entrega final.', '', 'Los controles automáticos son indicios; no certifican ausencia de halos ni fidelidad artística.', '', '## Pendientes','']
            summary += ['- '+i['path']+': '+'; '.join(i['issues']) for i in report['items'] if i['issues']]
            payload['assets/metadata/deliveries/barco-'+id_+'.md']=('\n'.join(summary)+'\n').encode()
            branch=name or 'codex/entrega-barco-'+time.strftime('%Y%m%d')+'-'+id_[:6]
            if not isinstance(branch,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]{1,100}',branch):raise ValueError('Nombre de rama inválido.')
            git(w.root,'check-ref-format','refs/heads/'+branch)
            env=dict(os.environ,GIT_INDEX_FILE=str(folder/'git-index'))
            git(w.root,'lfs','version');git(w.root,'read-tree',base,env=env)
            updates=[]
            for name,data in payload.items():
                safe_path(name);oid=git(w.root,'hash-object','-w','--path='+name,'--stdin',data=data,env=env).decode().strip()
                if name.endswith('.png') and not git(w.root,'cat-file','blob',oid).startswith(b'version https://git-lfs.github.com/spec/v1\n'):raise ValueError('Git LFS no está activo para los PNG; no se creó la rama.')
                updates.append('100644 '+oid+'\t'+name+'\n')
            git(w.root,'update-index','--index-info',data=''.join(updates).encode(),env=env)
            tree=git(w.root,'write-tree',env=env).decode().strip()
            commit=git(w.root,'commit-tree',tree,'-p',base,data=('Entrega barco: '+str(len(report['items']))+' assets · '+report['delivery_state']+'\n').encode()).decode().strip()
            git(w.root,'update-ref','refs/heads/'+branch,commit,'0'*40)
            report.update(branch=branch,commit=commit,pushed=False);self.report=report;self.persist()
            return report
    def push(self,id_):
        with self.lock:
            r=self.report
            if not r or r.get('id')!=id_ or not r.get('branch'):raise ValueError('Primero creá la rama de esta entrega.')
            if git(self.work.root,'rev-parse','refs/heads/'+r['branch']).decode().strip()!=r['commit']:raise ValueError('La rama cambió; revisá antes de enviar.')
            git(self.work.root,'push','origin','refs/heads/'+r['branch']+':refs/heads/'+r['branch'])
            r['pushed']=True;self.persist();return copy.deepcopy(r)
