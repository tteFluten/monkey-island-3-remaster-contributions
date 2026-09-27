"""Explicit, single-asset ImageLab jobs. Provider output stays separate until accepted."""
import base64
import io
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
from functools import lru_cache
import hashlib
from spriteprep import clean_base
from spritequality import assess_fidelity, palette_description

@lru_cache(maxsize=4096)
def candidate_hash(path, modified):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ImageLab:
    def __init__(self, workshop, atomic_write, sha, png_size, conflict):
        self.work = workshop
        self.atomic_write=atomic_write;self.sha=sha;self.png_size=png_size;self.conflict=conflict
        self.root = workshop.store / 'imagelab'
        self.lock = threading.RLock()
        self.probe_lock = threading.Lock()
        self.cached = None
        self.active = None

    def resume(self):
        with self.lock:
            for path in self.root.glob('*/job.json'):
                job=json.loads(path.read_text(encoding='utf-8'))
                if job['status']=='running':
                    job.update(status='interrupted',error='El servidor se reinició durante la generación. Revisá el proveedor antes de repetir.')
                    self.write(job)
            self.start_next()

    def start_next(self):
        with self.lock:
            if self.active: return
            queued=sorted((j for j in self.list() if j['status']=='queued'),key=lambda j:j['created_at'])
            if not queued: return
            job=queued[0];self.active=job['id']
            job['status']='running';self.write(job)
            threading.Thread(target=self.run,args=(job,),daemon=True).start()

    def cancel(self, id_):
        with self.lock:
            job=self.read(id_)
            if job['status']!='queued': raise ValueError('Solo se pueden quitar trabajos que todavía estén en espera.')
            job['status']='cancelled';self.write(job)
            return job

    def worker(self, mode, folder=None):
        node = shutil.which('node')
        if not node: raise ValueError('Se necesita Node.js para conectar con el MCP de ImageLab.')
        args = [node, str(Path(__file__).with_name('imagelab-worker.mjs')), str(self.work.root), mode]
        if folder: args.append(str(folder))
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                timeout=45 if mode == 'probe' else 660,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise ValueError('ImageLab no respondió a tiempo. No se reintentó automáticamente; revisá el proveedor antes de repetir.')
        try: response = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError): raise ValueError('No se pudo leer la respuesta del cliente MCP.')
        if not response.get('ready'): raise ValueError(response.get('error', 'No se pudo conectar con ImageLab.'))
        return response

    def status(self):
        with self.probe_lock:
            if self.cached and time.monotonic() - self.cached[0] < 60: return self.cached[1]
            try: result = self.worker('probe')
            except ValueError as error: result = dict(ready=False, error=str(error))
            self.cached = time.monotonic(), result
            return result

    def folder(self, id_):
        if not isinstance(id_, str) or not re.fullmatch(r'[a-f0-9]{24}', id_): raise ValueError('Trabajo desconocido.')
        return self.root / id_

    def read(self, id_):
        folder = self.folder(id_)
        result = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        if result['status'] in ('ready', 'applied'):
            result['image'] = '/api/imagelab/image?id=' + id_
            result['raw_image'] = result['image'] + '&raw=1'
            candidate=folder/'candidate.png'
            if candidate.exists():result['candidate_sha256']=candidate_hash(str(candidate),candidate.stat().st_mtime_ns)
        return result

    def write(self, job):
        self.atomic_write(self.folder(job['id'])/'job.json', json.dumps(job, ensure_ascii=False).encode())

    def list(self, asset=None):
        if asset: self.work.frame(asset)
        jobs=[]
        for path in self.root.glob('*/job.json'):
            job=self.read(path.parent.name)
            if not asset or job['asset_id']==asset: jobs.append(job)
        return sorted(jobs,key=lambda job:job['created_at'],reverse=True)

    def create(self, body):
        atomic_write,sha,png_size=self.atomic_write,self.sha,self.png_size
        try: from PIL import Image
        except ImportError: raise ValueError('Instalá Pillow antes de generar: python -m pip install Pillow')
        asset=body['id'];self.work.frame(asset)
        prompt=body.get('prompt','')
        if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=3000: raise ValueError('Escribí una instrucción de hasta 3000 caracteres.')
        config=self.status()
        if not config.get('ready'): raise ValueError(config['error'])
        model=body.get('model') or config.get('defaultModel')
        if model not in config.get('models',[]): raise ValueError('Modelo no disponible en este MCP.')
        with self.lock, self.work.lock:
            source=self.work.draft(asset) if self.work.draft(asset).exists() else self.work.original(asset)
            current=source.read_bytes();width,height=png_size(current)
            ref=self.work.reference(asset)
            if not ref: raise ValueError('No hay original asociado a este asset. No se enviará el remaster defectuoso como base.')
            reference=ref.read_bytes();png_size(reference)
            with Image.open(io.BytesIO(reference)) as original:
                original=original.convert('RGBA')
                if abs(original.width/original.height-width/height)>.02*(width/height):
                    raise ValueError('El original y el master tienen proporciones distintas. Revisá la asociación antes de generar.')
                upscale_job=None
                base_kind=body.get('base_kind','original')
                history_name=body.get('base_history')
                if base_kind not in ('original','current','history'):raise ValueError('Base desconocida.')
                if body.get('upscale_job_id'):
                    upscale_job=self.read(body['upscale_job_id'])
                    if (upscale_job['asset_id']!=asset
                        or upscale_job['status'] not in ('ready','applied')
                        or (upscale_job.get('original_sha256') and upscale_job['original_sha256']!=sha(reference))):
                        raise ValueError('La versión no corresponde a este original o todavía no está disponible.')
                    with Image.open(self.folder(upscale_job['id'])/'candidate.png') as image:
                        base=image.convert('RGBA')
                        if abs(base.width/base.height-width/height)>.02*(width/height):
                            raise ValueError('La versión tiene proporciones incompatibles con este asset.')
                elif base_kind=='current':
                    if body.get('base_revision')!=self.work.revision(asset):raise self.conflict('La versión en uso cambió. Volvé a seleccionarla antes de generar.')
                    with Image.open(io.BytesIO(current)) as image:base=image.convert('RGBA')
                elif base_kind=='history':
                    if not isinstance(history_name,str) or not re.fullmatch(r'\d+-before\.png',history_name):raise ValueError('Versión guardada inválida.')
                    with Image.open(self.work.store/'history'/asset/history_name) as image:base=image.convert('RGBA')
                    if base.size!=(width,height):raise ValueError('La versión guardada tiene dimensiones incompatibles.')
                else:
                    base=clean_base(original,(width,height))
                buffer=io.BytesIO();base.save(buffer,format='PNG');base_png=buffer.getvalue()
                # Preserve a known rectangular viewport inside a square provider canvas.
                factor=896/max(original.size)
                bw,bh=max(1,round(original.width*factor)),max(1,round(original.height*factor))
                enlarged=base.resize((bw,bh),Image.Resampling.BICUBIC) if upscale_job or base_kind!='original' else clean_base(original,(bw,bh))
                prepared=Image.new('RGBA',(1024,1024),(128,128,128,255))
                bx,by=(1024-bw)//2,(1024-bh)//2
                prepared.alpha_composite(enlarged,(bx,by))
                buffer=io.BytesIO();prepared.save(buffer,format='PNG')
            images=[dict(base64=base64.b64encode(buffer.getvalue()).decode(),label='subject')]
            style_frame=None
            approved=self.approvals()
            candidates=[f for f in self.work.frames.values() if f['id']!=asset and f['group']==self.work.frame(asset)['group']
                and (f['id'] in approved or f.get('review',{}).get('current') and f.get('review',{}).get('state')=='accepted')]
            candidates.sort(key=lambda f:abs(f.get('number',0)-self.work.frame(asset).get('number',0)))
            selected_style=body.get('style_id')
            if selected_style:
                candidate=self.work.frame(selected_style)
                if selected_style not in approved and not (candidate.get('review',{}).get('current') and candidate.get('review',{}).get('state')=='accepted'):
                    raise ValueError('La referencia elegida no está aprobada.')
                candidates=[candidate]
            if selected_style=='': candidates=[]
            for candidate in candidates:
                try:
                    approval=approved.get(candidate['id'])
                    style=(self.root/'references'/approval['file']).read_bytes() if approval else self.work.original(candidate['id']).read_bytes()
                    sw,sh=png_size(style)
                    if not selected_style and not .5<(sw/sh)/(width/height)<2: continue
                    # Only use the reviewed master, never an unreviewed local draft.
                    if sha(style)!=(approval['sha256'] if approval else candidate['review'].get('sha256')): continue
                    style_frame=candidate
                    images.append(dict(base64=base64.b64encode(style).decode(),label='style ref'));break
                except (OSError,ValueError): continue
            if selected_style and not style_frame: raise ValueError('La referencia aprobada cambió o no está disponible.')
            # Supply the untouched color/ink samples too: preprocessing alone blurs
            # thin dark lines and changes the apparent proportions of color regions.
            authority=Image.new('RGBA',(1024,1024),(128,128,128,255))
            authority.alpha_composite(original.resize((bw,bh),Image.Resampling.NEAREST),(bx,by))
            authority_bytes=io.BytesIO();authority.save(authority_bytes,format='PNG')
            images.append(dict(base64=base64.b64encode(authority_bytes.getvalue()).decode(),label='photo ref'))
            original_index=len(images)
            ratio='1:1'
            instruction=('Faithfully remaster the original game sprite in @1. @1 is the ONLY authority for content, pose, silhouette, palette, framing and proportions. '
                'The base is a sampled low-resolution drawing, NOT intentional pixel art. Reconstruct the continuous drawing those samples represent. '
                'Remove ALL square pixel blocks, stepped outlines, mosaic patches and rectangular color tiles. Use a small number of coherent, smooth hand-painted color regions and long clean contours. '
                'This may be a partial animation cel or an object fragment: NEVER complete it into a whole character or object. '
                + f'@{original_index} contains the UNALTERED original samples at exactly the same placement. It is the final authority for exact colors, darkness, local shading and INK WIDTH; @1 only helps interpolate the silhouette. '
                + 'Original dominant opaque RGB colors: '+palette_description(original)+'. Preserve these colors and their spatial regions. Do not brighten, saturate, tint, relight, add highlights or replace shading. '
                + 'Preserve the original outline color and relative thickness, including tapering. A line one source pixel wide stays one source pixel wide at the corresponding scale. Do not add outlines to regions that had none. No bold cartoon stroke, bevels or extra wood grain. '
                + ('@2 is an optional finish example ONLY. Do NOT borrow its line thickness, colors, lighting, geometry or surface detail. Ignore it whenever it conflicts with the original. ' if style_frame else '')
                + f'Output the complete SQUARE canvas of @1. The sprite viewport is x={bx}, y={by}, width={bw}, height={bh} on a 1024x1024 canvas. '
                'Keep the overall silhouette and bounding box at the SAME normalized coordinates, but replace pixel stair steps with simple straight lines or smooth curves. Do not zoom, recenter, enlarge or crop the object. '
                'Keep the neutral gray background and margins exactly unchanged. The gray is a processing matte, not part of the artwork. '
                'Only interpolate sampling stair steps into continuous edges; retain every original color region and its contrast. Do NOT preserve the source pixel grid. No photorealistic texture or invented 3D volume. '
                'No added objects, text or scenery. User description and instruction: '+prompt.strip())
            id_=secrets.token_hex(12);folder=self.folder(id_);folder.mkdir(parents=True)
            atomic_write(folder/'input.png',base_png)
            atomic_write(folder/'original.png',reference)
            atomic_write(folder/'prepared.png',buffer.getvalue())
            if style_frame: atomic_write(folder/'style.png',style)
            request=dict(prompt=instruction,images=images,model=model,aspect_ratio=ratio,image_size='1K')
            atomic_write(folder/'request.json',json.dumps(request).encode())
            job=dict(id=id_,asset_id=asset,asset_name=self.work.frame(asset)['name'],prompt=prompt.strip(),model=model,
                width=width,height=height,base_revision=self.work.revision(asset),source_sha256=sha(current),
                created_at=time.time(),status='queued',preserve_alpha=body.get('preserve_alpha',True) is True,
                base_kind='generation' if upscale_job else base_kind,base_history=history_name if base_kind=='history' else None,fidelity_version=2,preparation='square-v1',alpha_mode='ai' if body.get('alpha_mode')=='ai' else 'original',mask_method='simplified-contour-v1',viewport=[bx,by,bw,bh],style_asset_id=style_frame['id'] if style_frame else None,
                style_asset_name=style_frame['name'] if style_frame else None,
                upscale_job_id=upscale_job['id'] if upscale_job else None)
            self.write(job);self.start_next()
            return job

    def create_upscale(self, body):
        from PIL import Image
        import replicate_upscale
        import topaz_wonder
        asset=body['id'];frame=self.work.frame(asset)
        enhance_model=body.get('enhance_model','CGI')
        direct = enhance_model in (topaz_wonder.MODEL,topaz_wonder.BRIA_MODEL)
        if enhance_model==topaz_wonder.BRIA_MODEL: replicate_upscale.token(self.work.root)
        provider = topaz_wonder if direct else replicate_upscale
        provider.token(self.work.root)
        if enhance_model not in ('CGI','Standard V2','Low Resolution V2','High Fidelity V2','Text Refine',replicate_upscale.ANIME_MODEL,topaz_wonder.MODEL,topaz_wonder.BRIA_MODEL):
            raise ValueError('Modelo de escalado no disponible.')
        with self.lock, self.work.lock:
            pending=next((j for j in self.list(asset) if j.get('operation')=='upscale' and j.get('enhance_model','CGI')==enhance_model and j['status'] in ('queued','running')),None)
            if pending: return pending
            reference=self.work.reference(asset)
            if not reference: raise ValueError('No hay original asociado; no se enviará el remaster como base.')
            original_bytes=reference.read_bytes()
            current=(self.work.draft(asset) if self.work.draft(asset).exists() else self.work.original(asset)).read_bytes()
            width,height=self.png_size(current)
            with Image.open(io.BytesIO(original_bytes)) as original:
                if (original.width*4,original.height*4)!=(width,height):
                    raise ValueError('Este asset no tiene dimensiones originales ×4; revisá la asociación.')
                prepared=provider.prepare_input(original)
            id_=secrets.token_hex(12);folder=self.folder(id_);folder.mkdir(parents=True)
            self.atomic_write(folder/'original.png',original_bytes)
            prepared.save(folder/'input.png')
            job=dict(id=id_,asset_id=asset,asset_name=frame['name'],operation='upscale',
                model=('' if enhance_model==replicate_upscale.ANIME_MODEL else 'Topaz ')+enhance_model+' ×4 · Replicate',enhance_model=enhance_model,prompt='Escalado ×4 del original, sin prompt. Alfa original interpolado.',
                base_kind='original',width=width,height=height,base_revision=self.work.revision(asset),
                source_sha256=self.sha(current),original_sha256=self.sha(original_bytes),
                created_at=time.time(),status='queued',alpha_mode='original',fidelity_version=2)
            if direct:
                job.update(provider='topaz-direct',model='Topaz · Wonder 3.5 High ×4 + Object Matting',
                    prompt='Original → Wonder 3.5 High ×4 → Object Matting. Se conserva RGB y alpha del proveedor.',alpha_mode='provider')
                if enhance_model==topaz_wonder.BRIA_MODEL:
                    job.update(model='Wonder 3.5 High ×4 + Bria · Replicate',prompt='Wonder desde el original; transparencia Bria y eliminación del gris en bordes semitransparentes.')
                    for previous in self.list(asset):
                        raw=self.folder(previous['id'])/'wonder.png'
                        if previous.get('original_sha256')==job['original_sha256'] and previous.get('provider')=='topaz-direct' and raw.exists():
                            with Image.open(raw) as cached:
                                if cached.size!=(width,height): continue
                            self.atomic_write(folder/'wonder.png',raw.read_bytes())
                            job['wonder_reused_from']=previous['id'];break
            self.write(job);self.start_next();return job

    def refine_alpha(self, body):
        from PIL import Image
        amount=float(body.get('trim_pixels',.5))
        if not math.isfinite(amount) or not 0<=amount<=3:raise ValueError('Recorte inválido: usá entre 0 y 3 píxeles.')
        protect=bool(body.get('protect_dark',True))
        tint=float(body.get('tint_strength',0))
        seams=bool(body.get('protect_seams',True))
        magenta=body.get('remove_magenta') is True
        outline=body.get('outline')
        if outline not in (None,'white-2','red-4'):raise ValueError('Contorno desconocido.')
        if outline:seams=False;magenta=False;amount=0;tint=0
        if not math.isfinite(tint) or not 0<=tint<=1:raise ValueError('Intensidad de tinte inválida.')
        with self.lock,self.work.lock:
            asset=body['id'];frame=self.work.frame(asset)
            if body.get('job_id'):
                source=self.read(body['job_id'])
                if source['asset_id']!=asset or source['status'] not in ('ready','applied'): raise ValueError('Versión no disponible.')
                path=self.folder(source['id'])/'candidate.png'
            elif body.get('history'):
                name=body['history']
                if not re.fullmatch(r'\d+-before\.png',name): raise ValueError('Versión inválida.')
                path=self.work.store/'history'/asset/name
            else:
                if body.get('revision')!=self.work.revision(asset): raise self.conflict('El asset cambió. Volvé a seleccionarlo.')
                path=self.work.draft(asset) if self.work.draft(asset).exists() else self.work.original(asset)
            data=path.read_bytes();width,height=self.png_size(data)
            digest=self.sha(data)
            reference=self.work.reference(asset) if seams else None
            if seams and not reference:raise ValueError('No hay original para proteger empalmes. Desactivá la protección para limpiar sin ella.')
            reference_data=reference.read_bytes() if reference else None
            reference_hash=self.sha(reference_data) if reference_data else None
            pending=next((j for j in self.list(asset) if j.get('operation') in ('local-alpha','local-outline') and j.get('outline')==outline and j.get('remove_magenta',False)==magenta and j.get('alpha_source_sha256')==digest and j.get('trim_pixels')==amount and j.get('protect_dark')==protect and j.get('tint_strength',0)==tint and j.get('protect_seams',False)==seams and j.get('alpha_reference_sha256')==reference_hash and j['status'] in ('queued','running')),None)
            if pending:return pending
            id_=secrets.token_hex(12);folder=self.folder(id_);folder.mkdir(parents=True)
            self.atomic_write(folder/'alpha-source.png',data)
            if reference_data:self.atomic_write(folder/'alpha-reference.png',reference_data)
            current=self.work.draft(asset) if self.work.draft(asset).exists() else self.work.original(asset)
            job=dict(id=id_,asset_id=asset,asset_name=frame['name'],operation='local-outline' if outline else 'local-alpha',
                model=({'white-2':'Contorno blanco · 2 px','red-4':'Contorno rojo · 4 px'}[outline] if outline else ('Quitar magenta · ' if magenta else '')+f'Limpieza de borde · {amount:g} px'+(f' · tinte {tint:.0%}' if tint else '')+(' · proteger oscuro' if protect else '')),alpha_mode='local',width=width,height=height,
                outline=outline,remove_magenta=magenta,trim_pixels=amount,protect_dark=protect,tint_strength=tint,protect_seams=seams,alpha_reference_sha256=reference_hash,
                alpha_source_sha256=digest,source_sha256=self.sha(current.read_bytes()),
                base_revision=self.work.revision(asset),parent_job=body.get('job_id'),history_source=body.get('history'),
                status='queued',created_at=time.time(),prompt='Recorte de alpha y tinte opcional del borde con tinta oscura cercana; interior intacto.')
            self.write(job);self.start_next();return job

    def select_variant(self, body):
        with self.lock,self.work.lock:
            job=self.read(body['job_id'])
            if job['status'] not in ('ready','applied'): raise ValueError('La variante no está terminada.')
            asset=job['asset_id']
            result=self.work.save(dict(id=asset,revision=body.get('revision'),
                png='data:image/png;base64,'+base64.b64encode((self.folder(job['id'])/'candidate.png').read_bytes()).decode(),
                offset=self.work.metadata(asset).get('offset',[0,0])),
                selected_variant=dict(job_id=job['id'],model=job['model'],operation=job.get('operation')))
            job.update(status='applied',applied_at=time.time());self.write(job)
            return dict(asset_id=asset,**result)

    def approvals(self):
        path=self.root/'references.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    def approve(self, body):
        with self.lock,self.work.lock:
            job=self.read(body['job_id']) if body.get('job_id') else None
            asset=job['asset_id'] if job else body['id'];frame=self.work.frame(asset)
            if job:
                if job['status'] not in ('ready','applied'): raise ValueError('La variante todavía no está lista.')
                if job.get('quality',{}).get('passed') is False: raise ValueError('Esta variante no respeta el original y no puede ser una referencia aprobada.')
                data=(self.folder(job['id'])/'candidate.png').read_bytes()
            else:
                if body.get('revision')!=self.work.revision(asset): raise self.conflict('El asset cambió. Volvé a revisarlo antes de aprobar.')
                path=self.work.draft(asset) if self.work.draft(asset).exists() else self.work.original(asset)
                data=path.read_bytes()
            self.png_size(data)
            approved=self.approvals();folder=self.root/'references';folder.mkdir(parents=True,exist_ok=True)
            digest=self.sha(data);filename=digest+'.png';self.atomic_write(folder/filename,data)
            record=dict(asset_id=asset,asset_name=frame['name'],sha256=digest,file=filename,approved_at=time.time(),job_id=job['id'] if job else None)
            approved[asset]=record
            self.atomic_write(self.root/'references.json',json.dumps(approved).encode())
            return record

    def revoke(self, asset):
        with self.lock:
            self.work.frame(asset);approved=self.approvals();approved.pop(asset,None)
            self.atomic_write(self.root/'references.json',json.dumps(approved).encode())
            return dict(ok=True)

    def run(self, job):
        try:
            job['status']='running';self.write(job)
            if job.get('operation') in ('local-alpha','local-outline'):
                from alpha_cleanup import run
                run(self,job)
            elif job.get('operation')=='refine-alpha':
                from topaz_wonder import refine_alpha
                refine_alpha(self,job)
            elif job.get('operation')=='upscale':
                if job.get('provider')=='topaz-direct':
                    from topaz_wonder import run
                else:
                    from replicate_upscale import run
                run(self,job)
            else:
                if job.get('operation')!='alpha-only': self.worker('generate',self.folder(job['id']))
                if job.get('alpha_mode')=='ai': self.extract_alpha(job)
                self.prepare(job)
            job['status']='ready';self.write(job)
        except Exception as error:
            job['status']='failed'
            job['error']=str(error) if isinstance(error,ValueError) else 'No se pudo preparar la variante. El asset original sigue intacto.'
            self.write(job)
        finally:
            with self.lock:
                self.active=None
                self.start_next()

    def alpha_variant(self, id_):
        with self.lock:
            source=self.read(id_)
            if source['status'] not in ('ready','applied'): raise ValueError('Primero debe terminar la generación.')
            if source.get('preparation')!='square-v1': raise ValueError('Esta variante es anterior al encuadre cuadrado; generá una nueva primero.')
            new_id=secrets.token_hex(12);folder=self.folder(new_id);folder.mkdir(parents=True)
            for name in ('provider-image.bin','input.png','original.png','prepared.png','style.png','request.json'):
                path=self.folder(id_)/name
                if path.exists(): self.atomic_write(folder/name,path.read_bytes())
            job={k:v for k,v in source.items() if k not in ('image','raw_image','applied_at','error','stage')}
            job.update(id=new_id,parent_job=id_,operation='alpha-only',alpha_mode='ai',status='queued',created_at=time.time())
            self.write(job);self.start_next();return job

    def extract_alpha(self, job):
        from PIL import Image
        folder=self.folder(job['id'])
        with Image.open(folder/'provider-image.bin') as image:
            if image.width*image.height>16_000_000 or abs(image.width/image.height-1)>.02:
                raise ValueError('La salida no tiene el lienzo esperado; no se envió a extraer alfa.')
            image.convert('RGBA').save(folder/'provider.png')
        job['stage']='extracting-alpha';self.write(job)
        # Same Gemini matte approach used by Basement Alpha Extractor; routed through MCP.
        prompt=('Generate a high-resolution grayscale alpha matte of the sprite in @1. '
            'The neutral gray BACKGROUND MUST become pure black (#000000), and ALL solid parts of the sprite, including its very dark outlines and dark wood, MUST be pure white (#FFFFFF). '
            'Dark colors inside the object are opaque material, NOT transparency. Preserve smooth antialiased edges using grayscale transitions. '
            'Do not redraw, simplify, expand, move, crop, or rescale the silhouette. Keep exactly the input image framing and square canvas. Return ONLY the grayscale matte.')
        request=dict(prompt=prompt,images=[dict(base64=base64.b64encode((folder/'provider.png').read_bytes()).decode(),label='subject')],model=job['model'],aspect_ratio='1:1',image_size='1K')
        self.atomic_write(folder/'alpha-request.json',json.dumps(request).encode())
        self.worker('alpha',folder)
        job['stage']='adapting';job['mask_method']='ai-generated-matte';self.write(job)

    def prepare(self, job):
        from PIL import Image, ImageOps, ImageChops
        folder=self.folder(job['id'])
        with Image.open(folder/'provider-image.bin') as generated:
            if generated.width*generated.height>16_000_000: raise ValueError('La imagen del proveedor excede el límite de 16 megapíxeles.')
            raw=generated.convert('RGBA');raw.save(folder/'provider.png')
            if job.get('alpha_mode')=='ai':
                with Image.open(folder/'alpha-image.bin') as matte_image:
                    if matte_image.width*matte_image.height>16_000_000 or abs(matte_image.width/matte_image.height-raw.width/raw.height)>.02:
                        raise ValueError('La máscara de IA cambió la proporción. No se aplicó.')
                    matte=matte_image.convert('L').resize(raw.size,Image.Resampling.LANCZOS)
                    matte=matte.point(lambda v:0 if v<8 else 255 if v>247 else v)
                    bbox=matte.getbbox()
                    if not bbox or matte.getextrema()[1]<200: raise ValueError('La IA no devolvió una máscara útil.')
                    corners=[matte.getpixel(p) for p in [(0,0),(raw.width-1,0),(0,raw.height-1),(raw.width-1,raw.height-1)]]
                    if max(corners)>32: raise ValueError('La máscara incluye el fondo; revisá la salida de alfa.')
                    matte.save(folder/'alpha.png');raw.putalpha(matte)
            if job.get('preparation')=='square-v1':
                if abs(raw.width/raw.height-1)>.02: raise ValueError('El proveedor cambió la proporción del lienzo. Se conservó la salida sin adaptarla.')
                x,y,w,h=job['viewport']
                box=(round(x*raw.width/1024),round(y*raw.height/1024),round((x+w)*raw.width/1024),round((y+h)*raw.height/1024))
                candidate=raw.crop(box).resize((job['width'],job['height']),Image.Resampling.LANCZOS)
            else:
                resized=ImageOps.contain(raw,(job['width'],job['height']),Image.Resampling.LANCZOS)
                candidate=Image.new('RGBA',(job['width'],job['height']))
                candidate.paste(resized,((candidate.width-resized.width)//2,(candidate.height-resized.height)//2))
            if job['preserve_alpha'] and job.get('alpha_mode')!='ai':
                with Image.open(folder/'input.png') as original:
                    alpha=original.convert('RGBA').getchannel('A')
                    candidate.putalpha(alpha if job.get('preparation')=='square-v1' else ImageChops.multiply(candidate.getchannel('A'),alpha))
            candidate.save(folder/'candidate.png')
            if job.get('fidelity_version')==2:
                with Image.open(folder/'original.png') as original:
                    job['quality']=assess_fidelity(original.convert('RGBA'),candidate)
            job['provider_size']=[raw.width,raw.height]

    def apply(self, id_):
        sha,Conflict=self.sha,self.conflict
        with self.lock, self.work.lock:
            job=self.read(id_)
            if job['status']=='applied': return dict(asset_id=job['asset_id'],already_applied=True)
            if job['status']!='ready': raise ValueError('La variante todavía no está lista.')
            if job.get('quality',{}).get('passed') is False:
                raise ValueError('Variante rechazada por fidelidad: '+', '.join(job['quality']['issues']))
            source=self.work.draft(job['asset_id']) if self.work.draft(job['asset_id']).exists() else self.work.original(job['asset_id'])
            if sha(source.read_bytes())!=job['source_sha256']: raise Conflict('El asset cambió desde la generación. La variante se conserva, pero no se reemplazó tu retoque.')
            data=(self.folder(id_)/'candidate.png').read_bytes()
            result=self.work.save(dict(id=job['asset_id'],revision=job['base_revision'],
                png='data:image/png;base64,'+base64.b64encode(data).decode(),offset=self.work.metadata(job['asset_id']).get('offset',[0,0])))
            job['status']='applied';job['applied_at']=time.time();self.write(job)
            return dict(asset_id=job['asset_id'],**result)



