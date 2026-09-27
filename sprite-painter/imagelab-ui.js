'use strict';
const imageLabDefaultPrompt='Interpolar el dibujo original a mayor resolución. Conservar sus colores exactos, luminosidad y regiones de sombreado. Mantener el color y grosor relativo de cada línea, sin engrosarla ni agregar contornos. Suavizar solo escalones de muestreo. No reinterpretar, completar fragmentos, cambiar materiales, agregar vetas o volumen. Respetar tamaño, pose y encuadre.';
const imageLabSending=new Set();
function imageLabPreferences(id){try{const settings=JSON.parse(localStorage.getItem('imagelab-settings-'+id)||'{}');if(settings.prompt==='Remasterizar fielmente el original. Conservar exactamente su silueta, pose, paleta y encuadre. Mejorar bordes y sombreado sin inventar formas ni completar fragmentos.')settings.prompt=imageLabDefaultPrompt;return settings;}catch{return {};}}
let imageLabAssetJobs=new Map(),imageLabApprovals={};
function syncImageLabAssets(jobs,approvals){
  imageLabApprovals=approvals||{};imageLabAssetJobs=new Map();
  for(const job of jobs){const old=imageLabAssetJobs.get(job.asset_id);if(!old||(['queued','running'].includes(job.status)&&!['queued','running'].includes(old.status)))imageLabAssetJobs.set(job.asset_id,job);}
  window.dispatchEvent(new Event('imagelab-assets'));
}
async function approveImageLabAsset(frame){
  try{
    if(imageLabApprovals[frame.id]){await api('/api/imagelab/revoke',{id:frame.id});delete imageLabApprovals[frame.id];imageLabNotice('Aprobación retirada · '+frame.name);}
    else{const info=await api('/api/open?id='+frame.id);const record=await api('/api/imagelab/approve',{id:frame.id,revision:info.revision});imageLabApprovals[frame.id]=record;imageLabNotice('Aprobado como referencia · '+frame.name);}
    window.dispatchEvent(new Event('imagelab-assets'));
  }catch(error){imageLabNotice(error.message);}
}
async function enqueueImageLab(frame,button){
  if(imageLabSending.has(frame.id))return;
  imageLabSending.add(frame.id);button.disabled=true;button.textContent='Enviando…';
  try{
    const job=await api('/api/imagelab/jobs',{id:frame.id,prompt:imageLabDefaultPrompt,preserve_alpha:true,alpha_mode:'ai',...imageLabPreferences(frame.id)});
    imageLabAssetJobs.set(frame.id,job);window.dispatchEvent(new Event('imagelab-assets'));
    imageLabNotice(frame.name+' · agregado a la cola');
  }catch(error){imageLabNotice('No se pudo agregar: '+error.message);}
  finally{imageLabSending.delete(frame.id);button.disabled=false;button.textContent='Retocar con ImageLab';window.dispatchEvent(new Event('imagelab-assets'));}
}
async function enqueueUpscale(frame,button){
  if(imageLabSending.has(frame.id))return;
  imageLabSending.add(frame.id);button.disabled=true;
  try{
    const job=await api('/api/upscale/jobs',{id:frame.id});
    imageLabAssetJobs.set(frame.id,job);imageLabNotice(frame.name+' · escalado del original en cola');
  }catch(error){imageLabNotice(error.message);}
  finally{imageLabSending.delete(frame.id);button.disabled=false;window.dispatchEvent(new Event('imagelab-assets'));}
}
async function showUpscale(frame,onApply,job){
  const dialog=document.createElement('dialog');dialog.className='imagelab-dialog';
  dialog.innerHTML='<div class="il-heading"><strong>Topaz ×4 · Replicate</strong><button data-close>Cerrar</button></div><p>Parte del original. No utiliza el remaster ni un prompt. El alfa conserva la silueta original con interpolación suave.</p><div class="il-images"><figure><figcaption>Original</figcaption><img data-original></figure><figure><figcaption>Escalado para revisar</figcaption><img data-result></figure></div><p data-status role="status"></p><button data-apply>Usar escalado y editar en Confite</button>';
  const q=k=>dialog.querySelector('[data-'+k+']');
  q('original').src='/api/reference?id='+frame.id;
  const close=()=>{dialog.close();dialog.remove();};q('close').onclick=close;
  document.body.append(dialog);dialog.showModal();
  const refresh=async()=>{
    if(!dialog.isConnected)return;
    try{
      job=await api('/api/imagelab/job?id='+job.id);
      q('status').textContent=job.error||(job.quality?.passed===false?'Rechazada por fidelidad: '+job.quality.issues.join(', '):imageLabStates[job.status]);
      q('apply').disabled=job.status!=='ready'||job.quality?.passed===false;
      cleanup.disabled=!['ready','applied'].includes(job.status)||job.quality?.passed===false;
      q('result').hidden=!job.image;if(job.image)q('result').src=job.image;
      if(['queued','running'].includes(job.status))setTimeout(refresh,2500);
    }catch(error){q('status').textContent=error.message;}
  };
  q('apply').disabled=true;
  const cleanup=document.createElement('button');cleanup.textContent='Limpiar este escalado con ImageLab…';cleanup.disabled=true;
  dialog.append(cleanup);
  cleanup.onclick=()=>{close();showImageLab(frame,onApply,null,job);};
  q('apply').onclick=async()=>{q('apply').disabled=true;try{await api('/api/imagelab/apply',{job_id:job.id});cache.delete(frame.id);close();await onApply();}catch(error){q('status').textContent=error.message;q('apply').disabled=false;}};
  await refresh();
  cleanup.disabled=!['ready','applied'].includes(job.status)||job.quality?.passed===false;
}
async function showImageLab(frame, onApply, selectedJob=null, upscaleJob=null){
  if(selectedJob){const job=await api('/api/imagelab/job?id='+selectedJob);if(job.operation==='upscale')return showUpscale(frame,onApply,job);}
  const dialog=document.createElement('dialog');dialog.className='imagelab-dialog';
  dialog.innerHTML='<div class="il-heading"><div><strong>Retocar con ImageLab</strong><p data-name></p></div><button data-close aria-label="Cerrar ImageLab">×</button></div><div class="il-images"><figure><figcaption>Asset actual</figcaption><img data-current></figure><figure><figcaption data-result-title>Variante para revisar</figcaption><img data-result hidden><p data-placeholder>La variante aparecerá acá. El original se conserva.</p></figure></div><label>Qué querés corregir<textarea data-prompt rows="3" maxlength="3000">Reparar deformaciones y artefactos del remaster. Recuperar la silueta, los rasgos y el trazo del original sin cambiar la pose, la paleta ni el encuadre.</textarea></label><div class="il-options"><label>Modelo<select data-model aria-label="Modelo ImageLab"></select></label><label><input data-alpha type="checkbox" checked> Conservar máscara de transparencia</label></div><p class="il-note">Envía el asset actual y, si existe, su referencia original al MCP de Basement. Generar consume el servicio del proveedor. Se adapta el resultado al tamaño del sprite sin estirarlo; revisá su alineación antes de usarlo.</p><div data-status role="status">Conectando con el MCP…</div><div class="il-history"><label>Variantes anteriores<select data-history aria-label="Variantes ImageLab"><option value="">Sin variantes</option></select></label><a data-raw target="_blank" rel="noopener" hidden>Ver salida sin adaptar</a></div><div class="il-footer"><button data-generate disabled>Generar variante</button><button data-apply class="accent" disabled>Usar variante y editar en Confite</button></div>';
  const get=key=>dialog.querySelector('[data-'+key+']');
  get('name').textContent=frame.name;get('current').src='/api/image?id='+frame.id;get('current').alt='Asset actual '+frame.name;get('result').alt='Variante de ImageLab';
  document.body.append(dialog);dialog.showModal();
  get('current').src='/api/reference?id='+frame.id;get('current').alt='Original del juego';dialog.querySelector('figcaption').textContent='Original · base del próximo envío';
  get('prompt').value=imageLabDefaultPrompt;
  dialog.querySelector('.il-note').textContent='ImageLab recibe el original ampliado dentro de un lienzo cuadrado gris, junto al ejemplo que elijas. La salida se recupera desde el mismo encuadre y conserva el alfa original. Describí qué representa el sprite, especialmente si es un fragmento. Revisá contornos y alineación antes de aplicar: la generación puede reinterpretarlos. Consume el servicio del proveedor.';
  get('generate').textContent='Agregar a la cola';
  const preferences=imageLabPreferences(frame.id);
  const alphaChoice=document.createElement('label');alphaChoice.innerHTML='Transparencia<select aria-label="Método de alfa"><option value="ai">IA · extraer del resultado</option><option value="original">Contorno original simplificado</option></select>';
  dialog.querySelector('.il-options').append(alphaChoice);const alphaMode=alphaChoice.querySelector('select');alphaMode.value=preferences.alpha_mode||'ai';
  get('alpha').closest('label').hidden=true;
  dialog.querySelector('.il-note').append(' El modo IA realiza un segundo llamado para extraer alfa del resultado.');
  get('prompt').value=preferences.prompt||imageLabDefaultPrompt;get('alpha').checked=preferences.preserve_alpha!==false;
  const example=document.createElement('div');example.className='il-example';
  example.innerHTML='<label>Ejemplo aprobado para estilo<select data-style><option value="">Solo original (sin ejemplo)</option></select></label><img data-style-image hidden alt="Ejemplo de estilo elegido"><small>Elegí un ejemplo visualmente parecido. Se copia su acabado, no su objeto ni su pose.</small>';
  dialog.querySelector('.il-options').before(example);
  const styleSelect=example.querySelector('select'),styleImage=example.querySelector('img');
  styleSelect.onchange=()=>{styleImage.hidden=!styleSelect.value;if(styleSelect.value)styleImage.src='/api/imagelab/reference?id='+styleSelect.value;};
  const saveSettings=document.createElement('button');saveSettings.textContent='Guardar configuración';dialog.querySelector('.il-footer').prepend(saveSettings);
  saveSettings.disabled=true;
  const settings=()=>({prompt:get('prompt').value,model:get('model').value,preserve_alpha:true,alpha_mode:alphaMode.value,style_id:styleSelect.value});
  saveSettings.onclick=()=>{try{localStorage.setItem('imagelab-settings-'+frame.id,JSON.stringify(settings()));imageLabNotice('Configuración guardada para este asset');}catch(error){status(error.message);}};
  get('current').src='/api/imagelab/prepared?id='+frame.id;dialog.querySelector('figcaption').textContent='Base preparada · contorno simplificado';
  if(upscaleJob){
    get('current').src=upscaleJob.image;dialog.querySelector('figcaption').textContent='Escalado Topaz · base para limpiar';
    dialog.querySelector('.il-note').textContent='Envía este escalado como base y el original intacto como autoridad de pose, paleta y grosor de línea. ImageLab puede reinterpretar el dibujo: revisá la variante antes de aplicarla. Consume el proveedor.';
  }
  let job=null,timer=null,generating=false,connected=false;
  const extract=document.createElement('button');extract.textContent='Reextraer alfa con IA';extract.disabled=true;dialog.querySelector('.il-footer').prepend(extract);
  const reuse=document.createElement('button');reuse.textContent='Usar esta configuración en el botón directo';reuse.hidden=true;dialog.querySelector('.il-footer').prepend(reuse);
  reuse.onclick=()=>{if(!job)return;const chosen={prompt:job.prompt,model:job.model,style_id:job.style_asset_id||'',preserve_alpha:true,alpha_mode:job.alpha_mode||'original'};try{localStorage.setItem('imagelab-settings-'+frame.id,JSON.stringify(chosen));get('prompt').value=chosen.prompt;get('model').value=chosen.model;styleSelect.value=chosen.style_id;styleSelect.onchange();alphaMode.value=chosen.alpha_mode;imageLabNotice('El botón directo usará el prompt, modelo, ejemplo y alfa de esta variante');}catch(error){status(error.message);}};
  extract.onclick=async()=>{extract.disabled=true;try{const sent=await api('/api/imagelab/alpha',{job_id:job.id});imageLabAssetJobs.set(frame.id,sent);window.dispatchEvent(new Event('imagelab-assets'));close();imageLabNotice('Extracción de alfa en cola · no se vuelve a generar el dibujo');}catch(error){status(error.message);extract.disabled=false;}};
  const status=text=>get('status').textContent=text;
  const close=()=>{clearTimeout(timer);dialog.close();dialog.remove();};get('close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  function render(value){
    job=value;generating=['running','queued'].includes(job.status);
    reuse.hidden=!['ready','applied'].includes(job.status);
    extract.disabled=!['ready','applied'].includes(job.status)||job.preparation!=='square-v1';
    get('result').hidden=true;get('placeholder').hidden=false;get('raw').hidden=true;
    get('generate').disabled=!connected;get('apply').disabled=!['ready','applied'].includes(job.status)||job.quality?.passed===false;
    get('current').src='/api/imagelab/image?id='+job.id+'&input=1';
    dialog.querySelector('figcaption').textContent=job.base_kind==='original'?'Original enviado':'Envío anterior · basado en el remaster';
    if(generating){status(job.status==='queued'?'En cola. Podés cerrar y seguir agregando otros assets.':job.stage==='extracting-alpha'?'Extrayendo alfa con IA del resultado…':'Generando. Podés cerrar y seguir trabajando; el resultado aparecerá en Cola de trabajos.');timer=setTimeout(poll,2000);}
    else if(job.status==='ready'||job.status==='applied'){
      get('result').src=job.image;get('result').hidden=false;get('placeholder').hidden=true;get('raw').href=job.raw_image;get('raw').hidden=false;
      status((job.status==='applied'?'Esta variante ya se aplicó como borrador.':'Variante lista · '+job.width+' × '+job.height+' px. ')+(job.base_kind==='original'?(job.style_asset_name?'Referencia de estilo aprobada: '+job.style_asset_name:'Solo original: no se encontró una referencia aprobada similar.'):'Generada con el flujo anterior. Un nuevo envío usará el original.'));
      if(job.quality?.passed===false)status('Rechazada por fidelidad: '+job.quality.issues.join(', ')+'. Se conserva para comparar; no se puede aplicar ni aprobar.');
    }else status(job.error||'No se completó la generación.');
  }
  async function poll(){if(!dialog.isConnected||!job)return;try{render(await api('/api/imagelab/job?id='+job.id));}catch(error){status(error.message);timer=setTimeout(poll,4000);}}
  get('generate').onclick=async()=>{
    get('generate').disabled=true;get('apply').disabled=true;status('Agregando a la cola…');
    get('result').hidden=true;get('placeholder').hidden=false;get('raw').hidden=true;clearTimeout(timer);
    try{const chosen=settings();const sent=await api('/api/imagelab/jobs',{id:frame.id,...chosen,...(upscaleJob?{upscale_job_id:upscaleJob.id}:{})});localStorage.setItem('imagelab-settings-'+frame.id,JSON.stringify(chosen));imageLabAssetJobs.set(frame.id,sent);window.dispatchEvent(new Event('imagelab-assets'));close();imageLabNotice('Agregado a la cola ImageLab');}
    catch(error){generating=false;get('generate').disabled=!connected;status(error.message);}
  };
  get('apply').onclick=async()=>{
    if(!job)return;get('apply').disabled=true;
    try{
      await api('/api/imagelab/apply',{job_id:job.id});cache.delete(frame.id);frame.edited=true;close();await onApply();
    }catch(error){status(error.message);get('apply').disabled=false;}
  };
  try{
    const history=await api('/api/imagelab/jobs?asset='+frame.id);
    if(!dialog.isConnected)return;
    const approved=history.approvals||{};
    for(const candidate of state.frames.filter(f=>approved[f.id]||f.review?.current&&f.review?.state==='accepted'))styleSelect.add(new Option(candidate.name,candidate.id));
    styleSelect.value=preferences.style_id||'';styleSelect.onchange();
    if(history.jobs.length){
      get('history').replaceChildren(new Option('Elegir una variante…',''));
      for(const item of history.jobs)get('history').add(new Option(new Date(item.created_at*1000).toLocaleString()+' · '+item.status,item.id));
      get('history').onchange=async()=>{if(!get('history').value)return;clearTimeout(timer);try{render(await api('/api/imagelab/job?id='+get('history').value));}catch(error){status(error.message);}};
      const pending=history.jobs.find(item=>item.id===selectedJob)||history.jobs.find(item=>['queued','running','ready','applied'].includes(item.status));if(pending)render(pending);
    }
    const connection=await api('/api/imagelab/status');
    if(!dialog.isConnected)return;
    connected=connection.ready;saveSettings.disabled=!connected;
    for(const model of connection.models||[])get('model').add(new Option(model,model));get('model').value=connection.defaultModel||connection.models?.[0]||'';
    if(connection.models?.includes(preferences.model))get('model').value=preferences.model;
    get('generate').disabled=!connected;if(!job)status(connected?'MCP conectado · listo para generar una variante.':connection.error);
  }catch(error){if(!job)status(error.message);else get('generate').title=error.message;}
}

const imageLabStates={queued:'En espera',running:'Generando',ready:'Lista para revisar',applied:'Aplicada',failed:'Falló',interrupted:'Interrumpida',cancelled:'Cancelada'};
function imageLabNotice(text){
  document.querySelector('.il-toast')?.remove();const notice=document.createElement('div');notice.className='il-toast';notice.setAttribute('role','status');notice.append(document.createTextNode(text+' · '));const open=document.createElement('button');open.textContent='Ver cola';open.onclick=()=>{notice.remove();showImageLabQueue();};notice.append(open);document.body.append(notice);setTimeout(()=>notice.remove(),10000);
}
async function showImageLabQueue(){
  const dialog=document.createElement('dialog');dialog.className='imagelab-dialog il-queue';
  dialog.innerHTML='<div class="il-heading"><div><strong>Cola de trabajos</strong><p data-summary>Consultando trabajos…</p></div><button data-close aria-label="Cerrar cola">×</button></div><p>Se procesan de a uno, en orden de envío. Podés cerrar y seguir agregando assets. Los resultados quedan guardados para revisar.</p><label>Mostrar <select data-filter><option value="all">Todos</option><option value="pending">En espera y generando</option><option value="ready">Listas para revisar</option><option value="failed">Con errores</option><option value="applied">Aplicadas</option></select></label><div data-message role="status"></div><div class="il-queue-grid" data-grid></div>';
  document.body.append(dialog);dialog.showModal();let timer,last='',jobs=[];
  const q=s=>dialog.querySelector('[data-'+s+']');
  const close=()=>{clearTimeout(timer);dialog.close();dialog.remove();};q('close').onclick=close;dialog.oncancel=e=>{e.preventDefault();close();};
  function render(){
    q('summary').textContent=jobs.filter(j=>j.status==='queued').length+' en espera · '+jobs.filter(j=>j.status==='running').length+' generando · '+jobs.filter(j=>j.status==='ready'&&j.quality?.passed!==false).length+' para revisar · '+jobs.filter(j=>j.quality?.passed===false).length+' rechazadas por fidelidad';
    const filter=q('filter').value,visible=jobs.filter(j=>filter==='all'||(filter==='pending'?['queued','running'].includes(j.status):filter==='failed'?['failed','interrupted'].includes(j.status)||j.quality?.passed===false:filter==='ready'?j.status==='ready'&&j.quality?.passed!==false:j.status===filter));
    q('grid').replaceChildren();
    if(!visible.length){q('grid').textContent='No hay trabajos en esta vista. Usá Retocar con ImageLab en cualquier asset para agregarlo.';return;}
    for(const job of visible){
      const card=document.createElement('article');card.className='il-job';
      const name=document.createElement('strong');name.textContent=job.asset_name;
      const status=document.createElement('p');status.textContent=(job.quality?.passed===false?'Rechazada por fidelidad':imageLabStates[job.status])+' · '+new Date(job.created_at*1000).toLocaleString();
      const images=document.createElement('div');images.className='il-images';
      for(const [label,url] of [['Enviado','/api/imagelab/image?id='+job.id+'&input=1'],['Resultado',job.image]]){
        const figure=document.createElement('figure'),caption=document.createElement('figcaption');caption.textContent=label;figure.append(caption);
        if(url){const img=document.createElement('img');img.src=url;img.alt=label+' '+job.asset_name;img.loading='lazy';figure.append(img);}else{const text=document.createElement('p');text.textContent=imageLabStates[job.status];figure.append(text);}images.append(figure);
      }
      const prompt=document.createElement('p');prompt.textContent=job.prompt;prompt.className='il-job-prompt';prompt.title=job.prompt;
      const recipe=document.createElement('p');recipe.textContent=job.model+' · '+(job.style_asset_name?'Ejemplo: '+job.style_asset_name:'Sin ejemplo')+' · '+(job.alpha_mode==='ai'?'Alfa IA':'Alfa original')+(job.quality?.passed===false?' · RECHAZADA: '+job.quality.issues.join(', '):'');recipe.className='il-job-prompt';
      const review=document.createElement('button');review.textContent='Comparar / revisar';review.onclick=async()=>{
        const frame=state.frames.find(f=>f.id===job.asset_id);if(!frame){q('message').textContent='El asset ya no está en el catálogo.';return;}
        close();await openAssetReview(frame,job.id);
      };
      card.append(name,status,images,recipe,prompt,review);
      if(['ready','applied'].includes(job.status)){
        const approve=document.createElement('button');const accepted=imageLabApprovals[job.asset_id]?.job_id===job.id;
        approve.textContent=accepted?'✓ Referencia aprobada':'Aprobar como referencia';approve.disabled=accepted||job.quality?.passed===false;
        approve.onclick=async()=>{approve.disabled=true;try{const record=await api('/api/imagelab/approve',{job_id:job.id});imageLabApprovals[job.asset_id]=record;window.dispatchEvent(new Event('imagelab-assets'));last='';await refresh();}catch(error){q('message').textContent=error.message;approve.disabled=false;}};card.append(approve);
      }
      if(job.error){const error=document.createElement('p');error.textContent=job.error;card.append(error);}
      if(job.status==='queued'){const cancel=document.createElement('button');cancel.textContent='Quitar de la cola';cancel.onclick=async()=>{try{await api('/api/imagelab/cancel',{job_id:job.id});last='';await refresh();}catch(error){q('message').textContent=error.message;}};card.append(cancel);}
      q('grid').append(card);
    }
  }
  q('filter').onchange=render;
  async function refresh(){clearTimeout(timer);if(!dialog.isConnected)return;try{const result=await api('/api/imagelab/jobs');if(!dialog.isConnected)return;syncImageLabAssets(result.jobs,result.approvals);const signature=JSON.stringify(result);if(signature!==last){jobs=result.jobs;last=signature;render();}}catch(error){q('message').textContent=error.message;}if(dialog.isConnected)timer=setTimeout(refresh,2500);}
  await refresh();
}
window.addEventListener('load',()=>{
  for(const host of [document.querySelector('header')].filter(Boolean)){
    const button=document.createElement('button');button.textContent='Cola de trabajos';button.onclick=showImageLabQueue;button.dataset.imagelabQueue='';host.append(button);
  }
  async function updateQueueBadge(){try{const {jobs,approvals}=await api('/api/imagelab/jobs');syncImageLabAssets(jobs,approvals);const pending=jobs.filter(j=>['queued','running'].includes(j.status)).length,ready=jobs.filter(j=>j.status==='ready'&&j.quality?.passed!==false).length;document.querySelectorAll('[data-imagelab-queue]').forEach(button=>{button.textContent='Cola de trabajos · '+pending+' pendientes · '+ready+' para revisar';});}catch{}setTimeout(updateQueueBadge,4000);}updateQueueBadge();
});
