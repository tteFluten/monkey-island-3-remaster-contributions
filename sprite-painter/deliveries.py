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

PR_REPOSITORY='ragojose/monkey-island-3-remaster'
PR_URL='https://github.com/'+PR_REPOSITORY+'.git'
PR_REMOTE='sprite-deliveries'
PR_BASE='refs/remotes/'+PR_REMOTE+'/main'

def digest(data):return hashlib.sha256(data).hexdigest()
def safe_path(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not name.startswith('assets/'):
        raise ValueError('Ruta de entrega inválida.')
    return p
def git(root,*args,data=None,env=None,github_auth=False):
    # Let Git invoke the official gh helper. Credentials are never read by this app.
    auth=['-c','credential.https://github.com.helper=','-c','credential.https://github.com.helper=!gh auth git-credential'] if github_auth else []
    try:
        result=subprocess.run(['git',*auth,'-C',str(root),*args],input=data,capture_output=True,env=env,timeout=600 if args[0]=='push' else 120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:raise ValueError('Git tardó demasiado en completar '+args[0]+'. El trabajo local se conserva; podés reintentar.')
    if result.returncode:raise ValueError('Git no pudo completar '+args[0]+'. Revisá identidad, permisos y acceso al remoto.')
    return result.stdout
def encode(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()

class Deliveries:
    def __init__(self,work,lab):
        self.work=work;self.lab=lab;self.root=work.store/'deliveries';self.lock=threading.RLock()
        self.progress=dict(running=False,done=0,total=0);self.report=None
        self.publication=dict(running=False,stage='',error=None)
        latest=self.root/'latest.json'
        if latest.exists():self.report=json.loads(latest.read_text(encoding='utf-8'))
    def persist(self):
        self.root.mkdir(parents=True,exist_ok=True)
        tmp=self.root/'latest.tmp';tmp.write_bytes(encode(self.report));tmp.replace(self.root/'latest.json')
    def snapshot(self):
        with self.lock:return dict(progress=dict(self.progress),publication=dict(self.publication),report=copy.deepcopy(self.report),target=dict(repository=PR_REPOSITORY,base='main'))
    def new_report(self,scope,ids):
        return dict(id=secrets.token_hex(12),scope=scope,selected_ids=ids,created_at=time.time(),status='checking',items=[],ready=0,blocked=0,repository=PR_REPOSITORY,base='main')
    def selected(self,manifest,scope,ids=None):
        if scope=='selection':
            wanted=set(ids or [])
            rows=[r for r in manifest['files'] if r.get('canonical') and digest(r['path'].encode())[:24] in wanted]
            found={digest(r['path'].encode())[:24] for r in rows}
            if wanted-found:raise ValueError('La selección incluye assets sin ruta canónica exportable. No se publicó nada.')
            if not rows:raise ValueError('Seleccioná al menos un asset.')
            return rows,[]
        plan=json.loads((self.work.root/'assets/metadata/topaz-scene-plan.json').read_text(encoding='utf-8'))
        rooms=['room-0009'] if scope=='interior' else ['room-0009','room-0010','room-0011']
        scenes=[s for s in plan['scenes'] if s['id'] in rooms]
        if len(scenes)!=len(rooms):raise ValueError('Falta el plan de una escena.')
        sources={s['source'] for scene in scenes for s in scene['sources']}
        rows=[r for r in manifest['files'] if r.get('canonical') and (r.get('source_id') in sources or (scope=='complete' and r['path'].startswith('assets/masters/') and '/objects/0003_' in r['path']) or r.get('asset_id') in ['background-room-'+str(int(x[-4:])) for x in rooms])]
        found={r.get('source_id') for r in rows}
        missing=sorted(sources-found)
        return rows,missing
    def start(self,scope='complete',ids=None):
        if scope not in ('complete','interior','selection'):raise ValueError('Alcance desconocido.')
        if scope=='selection':
            if not isinstance(ids,list) or not ids or len(ids)>10000 or any(not isinstance(i,str) or i not in self.work.frames for i in ids):raise ValueError('Selección inválida.')
            ids=list(dict.fromkeys(ids))
        with self.lock:
            if self.progress['running'] or self.publication['running']:raise ValueError('Ya hay una entrega en proceso.')
            previous={i['id']:i for i in (self.report or {}).get('items',[])}
            self.report=self.new_report(scope,ids)
            self.progress=dict(running=True,done=0,total=len(ids or []))
            self.publication=dict(running=False,stage='',error=None)
            threading.Thread(target=self.analyze,args=(scope,ids,previous),daemon=True).start()
        return self.snapshot()
    def analyze(self,scope,ids=None,previous=None):
        try:
            if previous is None:
                previous={i['id']:i for i in (self.report or {}).get('items',[])}
                with self.lock:self.report=self.new_report(scope,ids)
            report=self.report
            w=self.work;manifest=json.loads((w.root/'assets/manifest.json').read_text(encoding='utf-8'))
            rows,missing=self.selected(manifest,scope,ids)
            # Selection checks only local images/approvals. Refresh the target main when publishing.
            report.update(missing_sources=missing,base_commit=None if scope=='selection' else git(w.root,'rev-parse','origin/main^{commit}').decode().strip(),source_commit=git(w.root,'rev-parse','HEAD').decode().strip())
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
                            item['audit']=audit
                            if scope=='selection':item['warnings']=list(audit['issues'])
                            else:item['issues']+=audit['issues']
                        elif scope=='selection':item['warnings']=['Sin original asociado para control visual']
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
            with self.lock:self.report.update(status='failed',error=str(error) if isinstance(error,ValueError) else 'No se pudo preparar la entrega.');self.persist()
        finally:
            with self.lock:self.progress['running']=False
    def branch(self,id_,name=None,draft=False):
        requested_name=name
        with self.lock:
            report=copy.deepcopy(self.report)
            if self.progress['running'] or not report or report.get('id')!=id_ or report.get('status') not in ('ready','blocked'):raise ValueError('Primero terminá el análisis de la entrega.')
            if report['status']!='ready' and not draft:raise ValueError('La entrega tiene pendientes. Podés crear un borrador explícito o resolverlos y analizar de nuevo.')
            if report.get('missing_sources') or any(not i.get('records') for i in report['items']):raise ValueError('Faltan archivos o derivados exportables. Revisá el informe antes de crear la rama.')
            if report.get('branch'):return report
            w=self.work;folder=self.root/id_;approvals=self.lab.approvals()
            if not report.get('base_commit'):raise ValueError('Falta actualizar main del repositorio de destino. Usá Crear PR a main.')
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
                    if index.get(name,{}).get('sha256')!=record['sha256']:payload[name]=data
                    index[name]=record
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
            branch=requested_name or 'codex/entrega-barco-'+time.strftime('%Y%m%d')+'-'+id_[:6]
            if not isinstance(branch,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]{1,100}',branch):raise ValueError('Nombre de rama inválido.')
            git(w.root,'check-ref-format','refs/heads/'+branch)
            env=dict(os.environ,GIT_INDEX_FILE=str(folder/'git-index'))
            git(w.root,'lfs','version');git(w.root,'read-tree',base,env=env)
            updates=[]
            objects={}
            for name,data in payload.items():
                safe_path(name);key=(name.endswith('.png'),digest(data))
                oid=objects.get(key)
                if not oid:
                    oid=git(w.root,'hash-object','-w','--path='+name,'--stdin',data=data,env=env).decode().strip()
                    if name.endswith('.png') and not git(w.root,'cat-file','blob',oid).startswith(b'version https://git-lfs.github.com/spec/v1\n'):raise ValueError('Git LFS no está activo para los PNG; no se creó la rama.')
                    objects[key]=oid
                updates.append('100644 '+oid+'\t'+name+'\n')
            git(w.root,'update-index','--index-info',data=''.join(updates).encode(),env=env)
            tree=git(w.root,'write-tree',env=env).decode().strip()
            commit=git(w.root,'commit-tree',tree,'-p',base,data=('Entrega barco: '+str(len(report['items']))+' assets · '+report['delivery_state']+'\n').encode()).decode().strip()
            git(w.root,'update-ref','refs/heads/'+branch,commit,'0'*40)
            report.update(branch=branch,commit=commit,pushed=False);self.report=report;self.persist()
            return report
    def push(self,id_):
        with self.lock:
            r=copy.deepcopy(self.report)
            if not r or r.get('id')!=id_ or not r.get('branch'):raise ValueError('Primero creá la rama de esta entrega.')
        if git(self.work.root,'rev-parse','refs/heads/'+r['branch']).decode().strip()!=r['commit']:raise ValueError('La rama cambió; revisá antes de enviar.')
        remote=self.push_remote(r) if r.get('pr_target')==PR_REPOSITORY else 'origin'
        if r.get('scope')=='selection' and r.get('pr_target')!=PR_REPOSITORY:raise ValueError('Falta confirmar el repositorio de destino. Usá Crear PR a main.')
        git(self.work.root,'push',remote,'refs/heads/'+r['branch']+':refs/heads/'+r['branch'],github_auth=r.get('pr_target')==PR_REPOSITORY)
        with self.lock:
            if self.report.get('id')!=id_ or self.report.get('commit')!=r['commit']:raise ValueError('La rama se subió, pero cambió la entrega activa. Volvé a revisar la selección.')
            self.report['pushed']=True;self.persist();return copy.deepcopy(self.report)

    def start_pr(self,id_,title,draft=False):
        if not isinstance(title,str) or not title.strip() or len(title)>180:raise ValueError('Escribí un título de hasta 180 caracteres.')
        with self.lock:
            if self.publication['running']:return self.snapshot()
            if self.progress['running'] or not self.report or self.report.get('id')!=id_ or self.report.get('status') not in ('ready','blocked'):raise ValueError('Primero prepará y revisá la entrega.')
            if self.report.get('scope')=='selection' and (draft or self.report.get('status')!='ready'):raise ValueError('La selección debe estar aprobada y ser exportable para crear el PR.')
            if self.report.get('pr_url'):return self.snapshot()
            self.publication=dict(running=True,stage='Preparando rama y archivos LFS',error=None)
            threading.Thread(target=self.publish_pr,args=(id_,title.strip(),bool(draft)),daemon=True).start()
        return self.snapshot()

    def github(self,*args):
        try:
            options=dict(cwd=self.work.root,capture_output=True,text=True,encoding='utf-8',timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            result=subprocess.run(['gh',*args],**options)
        except FileNotFoundError:raise ValueError('Falta GitHub CLI. Instalá gh e iniciá sesión con gh auth login.')
        except subprocess.TimeoutExpired:raise ValueError('GitHub no confirmó la respuesta. Podés reintentar: se buscará primero un PR existente para esta rama.')
        if result.returncode:raise ValueError('GitHub no pudo completar la operación. Iniciá sesión con gh auth login y revisá el acceso al repositorio.')
        return result.stdout.strip()

    def target_remote(self):
        return self.ensure_remote(PR_REMOTE,PR_URL)

    def ensure_remote(self,name,url):
        remotes=git(self.work.root,'remote').decode().splitlines()
        if name not in remotes:git(self.work.root,'remote','add',name,url)
        # Validate fetch AND push destinations; never publish through an unrelated origin.
        for flags in ([],['--push']):
            urls=git(self.work.root,'remote','get-url',*flags,'--all',name).decode().splitlines()
            if urls!=[url]:raise ValueError('El remoto de entregas no coincide con el repositorio de destino. Revisá su configuración antes de publicar.')
        return name

    def prepare_pr_head(self,id_):
        target=json.loads(self.github('api','repos/'+PR_REPOSITORY))
        repository=PR_REPOSITORY
        if not target.get('permissions',{}).get('push'):
            login=self.github('api','user','--jq','.login')
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*',login):raise ValueError('GitHub no confirmó la cuenta para crear el fork.')
            fork_name=PR_REPOSITORY.split('/')[1]+'-contributions'
            repository=login+'/'+fork_name
            self.publication['stage']='Preparando fork '+repository
            self.github('repo','fork',PR_REPOSITORY,'--clone=false','--remote=false','--fork-name',fork_name)
            fork=json.loads(self.github('api','repos/'+repository))
            if fork.get('full_name','').lower()!=repository.lower() or not fork.get('fork') or fork.get('parent',{}).get('full_name')!=PR_REPOSITORY or not fork.get('permissions',{}).get('push'):
                raise ValueError('No se confirmó un fork propio con permiso de escritura. No se subieron assets.')
        with self.lock:
            if self.report.get('id')!=id_:raise ValueError('Cambió la selección. Verificala de nuevo.')
            self.report['push_repository']=repository
            self.report['pr_head']=self.report['branch'] if repository==PR_REPOSITORY else repository.split('/')[0]+':'+self.report['branch']
            self.persist()

    def push_remote(self,report):
        repository=report.get('push_repository')
        if repository==PR_REPOSITORY:return self.target_remote()
        if not isinstance(repository,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/'+re.escape(PR_REPOSITORY.split('/')[1]+'-contributions'),repository):
            raise ValueError('Falta preparar el fork de destino. Usá Crear PR a main.')
        return self.ensure_remote('sprite-delivery-fork','https://github.com/'+repository+'.git')

    def refresh_pr_base(self,id_):
        remote=self.target_remote()
        git(self.work.root,'fetch',remote,'+refs/heads/main:'+PR_BASE,github_auth=True)
        base=git(self.work.root,'rev-parse',PR_BASE+'^{commit}').decode().strip()
        with self.lock:
            if self.report.get('id')!=id_:raise ValueError('Cambió la selección. Verificala de nuevo.')
            if self.report.get('branch'):
                if self.report.get('pr_target')!=PR_REPOSITORY:raise ValueError('La rama pertenece a otro destino. Verificá la selección de nuevo.')
            else:self.report.update(base_commit=base,repository=PR_REPOSITORY,pr_target=PR_REPOSITORY,base='main');self.persist()

    def publish_pr(self,id_,title,draft):
        try:
            self.github('api','user','--jq','.login')
            self.publication['stage']='Actualizando '+PR_REPOSITORY+' · main'
            self.refresh_pr_base(id_)
            report=self.branch(id_,'codex/sprites-'+id_[:10],draft=draft)
            self.prepare_pr_head(id_)
            self.publication['stage']='Subiendo rama y archivos LFS'
            report=self.push(id_)
            self.publication['stage']='Creando PR a main'
            existing=json.loads(self.github('pr','list','--repo',PR_REPOSITORY,'--head',report['branch'],'--base','main','--state','open','--json','url,headRepositoryOwner'))
            owner=report['push_repository'].split('/')[0].lower()
            existing=[pr for pr in existing if pr.get('headRepositoryOwner',{}).get('login','').lower()==owner]
            if existing:url=existing[0]['url']
            else:
                body=self.root/id_/'pr-body.md'
                lines=['Actualiza '+str(len(report['items']))+' sprites con las versiones en uso del refinador y sus copias de runtime.','', 'La selección se exportó sobre `main`, sin código del editor ni variantes descartadas.','', 'Validación: PNG, dimensiones, hashes y almacenamiento Git LFS. El historial local se conserva.','', 'Revisión: '+str(report['ready'])+' sin pendientes; '+str(report['blocked'])+' con avisos o aprobación pendiente.','', 'Los controles automáticos no certifican la calidad visual.']
                body.write_text('\n'.join(lines)+'\n',encoding='utf-8')
                args=['pr','create','--repo',PR_REPOSITORY,'--base','main','--head',report['pr_head'],'--title',title,'--body-file',str(body)]
                if draft:args.append('--draft')
                url=self.github(*args).splitlines()[-1]
            if not re.fullmatch(re.escape('https://github.com/'+PR_REPOSITORY)+r'/pull/\d+',url):raise ValueError('GitHub no devolvió una URL de PR del repositorio de destino.')
            with self.lock:
                self.report['pr_url']=url;self.persist();self.publication['stage']='PR creado'
        except Exception as error:
            self.publication['error']=str(error) if isinstance(error,ValueError) else 'No se pudo publicar el PR. El trabajo local se conserva.'
        finally:self.publication['running']=False
