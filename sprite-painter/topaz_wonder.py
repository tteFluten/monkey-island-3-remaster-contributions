"""Direct Topaz Wonder + Object Matting; preserve provider RGB and alpha."""
import io
import json
import time
import uuid
import urllib.request
import urllib.error
from PIL import Image
from spritequality import assess_fidelity

MODEL = 'Wonder 3.5 High + Object Matting'
BRIA_MODEL = 'Wonder 3.5 High + Bria'
API = 'https://api.topazlabs.com'
WONDER = dict(model='Wonder 3.5', enhancementStrength='high', output_format='png', crop_to_fill='false', grain='false')
MATTING = dict(model='Object', mode='segmentation', output_format='png')

def token(root):
    path = root / '.context/secrets/topaz-api-key'
    if not path.exists(): raise ValueError('Falta la clave local de Topaz.')
    return path.read_text(encoding='utf-8').strip()

def request(root, route, fields=None, image=None):
    import subprocess
    import shutil
    key = token(root)
    if any(c in key for c in '\r\n"\\'):
        raise ValueError('Clave Topaz inválida.')
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if not curl: raise ValueError('Se necesita curl para conectar con Topaz.')
    args = [curl, '-sS', '--connect-timeout', '15', '--max-time', '180',
            '--config', '-', '-w', '\n%{http_code}', API + route]
    if fields is not None:
        args += ['-X', 'POST']
        for name, value in fields.items(): args += ['--form-string', f'{name}={value}']
    if image: args += ['-F', f'image=@{image};type=image/png']
    result = subprocess.run(args, input=f'header = "X-API-KEY: {key}"\n',
        capture_output=True, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('Conexión Topaz interrumpida. No se reintentó el envío; revisá el trabajo antes de repetir.')
    body, code = result.stdout.rsplit('\n', 1)
    if int(code)>=400:
        raise ValueError(f'Topaz respondió HTTP {code}. No se reintentó el envío.')
    try: return json.loads(body)
    except ValueError: raise ValueError('Respuesta de Topaz inválida; no se reintentó el envío.') from None

def prepare_input(original):
    rgba = original.convert('RGBA')
    matte = Image.new('RGB', rgba.size, (127,127,127))
    matte.paste(rgba, mask=rgba.getchannel('A'))
    return matte

def read_output(url, provider):
    """Retry only idempotent downloads, never paid prediction submissions."""
    if not isinstance(url,str) or not url.startswith('https://'):
        raise ValueError(f'URL de salida de {provider} inválida.')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=90) as response:
                data=response.read(64*1024*1024+1)
            if len(data)>64*1024*1024:raise ValueError(f'Salida de {provider} demasiado grande.')
            return data
        except (urllib.error.URLError,TimeoutError,ConnectionError):
            if attempt==2:
                raise ValueError(f'{provider} terminó, pero no se pudo descargar el resultado. El pedido quedó guardado; no se volvió a generar.') from None
            time.sleep(1+attempt)

def download(root, process_id, destination):
    response = request(root, '/image/v1/download/' + process_id)
    url = response.get('download_url') or response.get('url', '')
    if not url.startswith('https://'): raise ValueError('URL de salida de Topaz inválida.')
    # Signed download hosts never receive the API credential.
    data=read_output(url,'Topaz')
    with Image.open(io.BytesIO(data)) as image: image.load()
    destination.write_bytes(data)

def stage(queue, job, name, route, fields, source, destination):
    root = queue.work.root
    record = job.setdefault('topaz_stages', {}).setdefault(name, {})
    if not record.get('process_id'):
        if record.get('state') == 'submitting':
            raise ValueError('Envío Topaz sin confirmar. No se repetirá automáticamente.')
        record.update(state='submitting', settings=fields)
        job['stage']=name; queue.write(job)
        response = request(root, route, fields, source)
        record.update(process_id=response['process_id'], state='submitted'); queue.write(job)
    deadline = time.monotonic()+900
    while True:
        status = request(root, '/image/v1/status/'+record['process_id'])['status']
        if status == 'Completed': break
        if status in ('Failed','Cancelled'): raise ValueError('Topaz: '+status)
        if time.monotonic()>deadline: raise ValueError('Topaz sigue procesando; el ID quedó guardado. No se reenvió el trabajo.')
        time.sleep(3)
    download(root, record['process_id'], destination)
    record['state']='downloaded'; queue.write(job)

def run(queue, job):
    folder=queue.folder(job['id']); root=queue.work.root
    width,height=job['width'],job['height']
    with Image.open(folder/'original.png') as source: original=source.convert('RGBA')
    transparent=original.getchannel('A').getextrema()[0]<255
    bria=job.get('enhance_model')==BRIA_MODEL
    raw=folder/'wonder.png'
    reused=raw.exists() and (bool(job.get('wonder_reused_from')) or job.get('topaz_stages',{}).get('wonder',{}).get('state')=='downloaded')
    fields=dict(WONDER, output_width=width, output_height=height)
    estimates=[] if reused else [request(root,'/image/v1/estimate-gen',dict(fields,input_width=original.width,input_height=original.height))]
    if transparent and not bria:
        estimates.append(request(root,'/image/v1/estimate',dict(MATTING,category='Matting',input_width=width,input_height=height)))
    credits=sum(float(e['credits']) for e in estimates)
    if credits>2: raise ValueError('La estimación supera el límite de 2 créditos por variante. No se envió.')
    if credits and float(request(root,'/account/v1/credits/balance')['available_credits'])<credits:
        raise ValueError('Saldo de Topaz insuficiente para completar la variante.')
    job['estimated_credits']=credits; queue.write(job)
    if not reused: stage(queue,job,'wonder','/image/v1/enhance-gen/async',fields,folder/'input.png',raw)
    with Image.open(raw) as image:
        if image.size!=(width,height): raise ValueError('Wonder cambió las dimensiones; no se aplicó la salida.')
        enhanced=image.convert('RGB')
    provider=folder/'provider.png'
    if transparent and bria:
        candidate=bria_cutout(queue,job,raw,enhanced)
    elif transparent:
        stage(queue,job,'matting','/image/v1/matting/async',MATTING,raw,provider)
        with Image.open(provider) as image:
            if image.mode!='RGBA' or image.size!=(width,height): raise ValueError('Matting no devolvió RGBA con las dimensiones correctas.')
            candidate=image.copy()
        if candidate.convert('RGB').tobytes()!=enhanced.tobytes(): raise ValueError('Matting alteró el color de Wonder; salida conservada para revisión.')
    else:
        candidate=enhanced.convert('RGBA'); candidate.save(provider)
    candidate.save(folder/'candidate.png')
    job['quality']=assess_fidelity(original,candidate)
    job['provider_size']=list(candidate.size); job['stage']='complete'

def refine_alpha(queue,job):
    folder=queue.folder(job['id'])
    with Image.open(folder/'alpha-source.png') as image:source=image.convert('RGBA')
    with Image.open(folder/'input.png') as image:enhanced=image.convert('RGB')
    mask=bria_cutout(queue,job,folder/'input.png',enhanced).getchannel('A')
    source.putalpha(mask)
    source.save(folder/'candidate.png');source.save(folder/'provider.png')
    job['alpha_cleanup']='alpha-only-rgb-preserved'
    job['provider_size']=list(source.size);job['stage']='complete'

def bria_cutout(queue, job, raw, enhanced):
    import base64
    import replicate_upscale
    folder=queue.folder(job['id'])
    if (folder/'bria.png').exists():
        return compose_bria(queue,job,(folder/'bria.png').read_bytes(),enhanced)
    job['stage']='bria-alpha'; queue.write(job)
    if not job.get('bria_prediction_id'):
        if job.get('bria_submitting'): raise ValueError('Envío Bria sin confirmar; no se repetirá automáticamente.')
        job['bria_submitting']=True; queue.write(job)
        result=replicate_upscale.request(queue.work.root,'/models/bria/remove-background/predictions',{'input':{
            'image':'data:image/png;base64,'+base64.b64encode(raw.read_bytes()).decode(), 'preserve_alpha':True}})
        job['bria_prediction_id']=result['id']; queue.write(job)
    else: result=replicate_upscale.request(queue.work.root,'/predictions/'+job['bria_prediction_id'])
    deadline=time.monotonic()+900
    while result['status'] not in ('succeeded','failed','canceled'):
        if time.monotonic()>deadline: raise ValueError('Bria sigue procesando; la predicción quedó guardada. No se reenvió.')
        time.sleep(3)
        result=replicate_upscale.request(queue.work.root,'/predictions/'+job['bria_prediction_id'])
    if result['status']!='succeeded': raise ValueError('Bria no completó la extracción. No se reenvió.')
    url=result['output']; url=url[0] if isinstance(url,list) else url
    if not isinstance(url,str) or not url.startswith('https://'): raise ValueError('Salida Bria inválida.')
    data=read_output(url,'Bria')
    (folder/'bria.png').write_bytes(data)
    return compose_bria(queue,job,data,enhanced)

def compose_bria(queue,job,data,enhanced):
    folder=queue.folder(job['id'])
    with Image.open(io.BytesIO(data)) as image:
        if 'A' not in image.getbands() and 'transparency' not in image.info:
            raise ValueError('Bria no devolvió transparencia.')
        width,height=enhanced.size
        if abs(image.width*height-image.height*width)>max(width,height):
            raise ValueError('Bria cambió la proporción del lienzo; no se deformó la máscara.')
        job['bria_size']=list(image.size)
        alpha=image.convert('RGBA').getchannel('A')
        if image.size!=enhanced.size:
            alpha=alpha.resize(enhanced.size,Image.Resampling.LANCZOS)
        job['alpha_resized']=image.size!=enhanced.size
    # Remove the neutral input matte contribution at fractional coverage only.
    # Opaque Wonder paint remains byte-identical; never restore the original mask.
    import numpy as np
    rgb=np.asarray(enhanced).astype('float32'); a=np.asarray(alpha).astype('float32')/255
    rgb=np.clip((rgb-127*(1-a[...,None]))/np.maximum(a[...,None],1/255),0,255)
    rgb[a==0]=0
    candidate=Image.fromarray(np.rint(rgb).astype('uint8'),'RGB').convert('RGBA')
    candidate.putalpha(alpha); candidate.save(folder/'provider.png')
    job['alpha_cleanup']='neutral-matte-unmix-v1'
    return candidate
