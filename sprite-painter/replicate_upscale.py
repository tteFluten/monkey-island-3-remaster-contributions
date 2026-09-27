"""Prompt-free Topaz upscale. Credentials and prediction state remain server-side."""
import base64
import io
import json
import time
import urllib.error
import urllib.request
from PIL import Image
from spritequality import assess_fidelity

API = 'https://api.replicate.com/v1'
MODEL = 'topazlabs/image-upscale'
ANIME_MODEL = 'Real-ESRGAN Anime 6B'
ANIME_VERSION = '1b976a4d456ed9e4d1a846597b7614e79eadad3032e9124fa63859db0fd59b56'

def prediction_request(job, image):
    if job.get('enhance_model')==ANIME_MODEL:
        return '/predictions', {'version':ANIME_VERSION,'input':{
            'img':image,'version':'Anime - anime6B','scale':4,'face_enhance':False,'tile':0}}
    return '/models/'+MODEL+'/predictions', {'input':{
        'image':image,'enhance_model':job.get('enhance_model','CGI'),
        'upscale_factor':'4x','output_format':'png','subject_detection':'None','face_enhancement':False}}

def token(root):
    path = root / '.context/secrets/replicate-api-token'
    if not path.exists(): raise ValueError('Falta configurar la credencial local de Replicate.')
    return path.read_text(encoding='utf-8').strip()

def request(root, path, body=None):
    headers = {'Authorization': 'Bearer ' + token(root), 'User-Agent': 'monkey-sprite-workshop/1.0'}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(API + path, data=data, headers=headers), timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f'Replicate respondió HTTP {error.code}. Revisá crédito, acceso al modelo y credencial; no se reintentó el envío.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('No se pudo confirmar la respuesta de Replicate. Revisá Predictions antes de repetir; no se reenvió automáticamente.') from None

def prepare_input(original):
    # Extend edge RGB into transparent pixels without changing the source silhouette.
    # This avoids black/colored mattes bleeding into the upscaled drawing.
    import numpy as np
    rgba = np.asarray(original.convert('RGBA'))
    colors = rgba[..., :3].astype('float32').copy()
    known = rgba[..., 3] > 0
    if not known.any(): raise ValueError('El original está completamente vacío.')
    for _ in range(sum(original.size)):
        if known.all(): break
        sums = np.zeros_like(colors); counts = np.zeros(known.shape, dtype='float32')
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            mask = np.roll(known, (dy,dx), (0,1)); value = np.roll(colors, (dy,dx), (0,1))
            if dy==1: mask[0,:]=False
            if dy==-1: mask[-1,:]=False
            if dx==1: mask[:,0]=False
            if dx==-1: mask[:,-1]=False
            sums += value * mask[...,None]; counts += mask
        fill = ~known & (counts>0)
        colors[fill] = sums[fill] / counts[fill,None]; known |= fill
    return Image.fromarray(colors.round().astype('uint8'), 'RGB')

def run(queue, job):
    folder = queue.folder(job['id'])
    if not job.get('prediction_id'):
        job['stage']='submitting';queue.write(job)
        endpoint, payload=prediction_request(job,'data:image/png;base64,'+base64.b64encode((folder/'input.png').read_bytes()).decode())
        result = request(queue.work.root, endpoint, payload)
        job['prediction_id']=result['id'];queue.write(job)
    else:
        result = request(queue.work.root, '/predictions/' + job['prediction_id'])
    deadline = time.monotonic() + 900
    while result['status'] not in ('succeeded','failed','canceled'):
        if time.monotonic()>deadline: raise ValueError('Replicate sigue procesando. La predicción quedó registrada; revisala antes de repetir.')
        job['stage']='upscaling';queue.write(job);time.sleep(3)
        result = request(queue.work.root, '/predictions/' + job['prediction_id'])
    if result['status']!='succeeded': raise ValueError('El modelo no completó el escalado. Consultá la predicción ' + job['prediction_id'] + ' en Replicate.')
    output=result['output']
    if isinstance(output,list): output=output[0]
    if not isinstance(output,str) or not output.startswith('https://'): raise ValueError('Salida de Replicate inválida.')
    # Never forward the API credential to the file host.
    with urllib.request.urlopen(output, timeout=90) as response:
        raw=response.read(64*1024*1024+1)
    if len(raw)>64*1024*1024: raise ValueError('Salida demasiado grande.')
    with Image.open(io.BytesIO(raw)) as image:
        if image.size!=(job['width'],job['height']): raise ValueError('El modelo cambió las dimensiones esperadas. No se aplicó ni deformó la salida.')
        candidate=image.convert('RGBA');candidate.save(folder/'provider.png')
    with Image.open(folder/'original.png') as image:
        original=image.convert('RGBA')
        # Geometry comes exclusively from the original. Cubic interpolation keeps
        # intermediate alpha instead of thresholding or generating a new matte.
        candidate.putalpha(original.getchannel('A').resize(candidate.size, Image.Resampling.BICUBIC))
        candidate.save(folder/'candidate.png')
        job['quality']=assess_fidelity(original,candidate)
    job['provider_size']=list(candidate.size);job['stage']='complete'
