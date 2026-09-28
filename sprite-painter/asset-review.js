'use strict';
// One review surface per asset. Selecting a version only changes the preview.
let assetReview=null;
async function openAssetReview(frame, initialJob=null){
  if(assetReview){assetReview.close();}
  const panel=document.createElement('section');panel.className='ar-workspace';panel.setAttribute('aria-label','Comparación de asset');
  panel.innerHTML=`<header class="ar-header"><button data-back>Assets</button><div><small>COMPARAR Y REFINAR</small><h1 data-name></h1></div><span data-summary></span></header>
  <div class="ar-layout"><main class="ar-main"><div class="ar-toolbar"><span>Vista sincronizada</span><button data-fit>Ajustar</button><button data-minus aria-label="Alejar comparación">−</button><output data-zoom>100%</output><button data-plus aria-label="Acercar comparación">+</button><select data-background aria-label="Fondo de comparación"><option value="checker">Transparencia</option><option value="#999da3">Gris</option><option value="#fafafa">Blanco</option><option value="#17191d">Oscuro</option><option value="#ff00ff">Magenta</option></select></div>
  <div class="ar-canvases"><figure><figcaption><strong>Original</strong><span data-original-size></span></figcaption><div class="ar-image-area"><img data-original alt="Original del juego" draggable="false"></div></figure><figure><figcaption><strong data-version-title>Resultado</strong><span data-result-size></span></figcaption><div class="ar-image-area"><img data-result alt="Versión seleccionada" draggable="false"><p data-empty hidden></p></div></figure></div>
  <div class="ar-bottom"><p data-status role="status"></p><div class="ar-version-actions"><button data-use>Usar esta versión</button><button data-layer>Enviar como capa a Confite</button><button data-manual class="accent">Retocar en Confite</button></div></div></main>
  <aside class="ar-sidebar"><section class="ar-generate"><h2>Crear otra versión</h2><label>Modelo<select data-model aria-label="Modelo para nueva versión"><optgroup label="Topaz · API directa"><option value="upscale:Wonder 3.5 High + Bria">Wonder 3.5 High ×4 + Bria</option></optgroup><optgroup label="Escalado · Replicate"><option value="upscale:Real-ESRGAN Anime 6B">Real-ESRGAN · Anime 6B ×4</option><option value="topaz:CGI">Topaz · CGI</option><option value="topaz:High Fidelity V2">Topaz · Alta fidelidad</option><option value="topaz:Standard V2">Topaz · Estándar</option><option value="topaz:Low Resolution V2">Topaz · Baja resolución</option></optgroup></select></label><div data-ai-options hidden><label>Base<select data-base aria-label="Base para ImageLab"><option value="original">Original</option></select></label><label>Instrucciones<textarea data-prompt rows="3"></textarea></label></div><p data-recipe>Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.</p><button data-generate class="accent">Generar versión</button><p data-message role="status"></p></section>
  <section class="ar-versions"><div class="ar-section-title"><h2>Versiones</h2><span data-count></span></div><p class="ar-hint">Seleccioná para comparar. El trabajo actual solo cambia al usar o retocar una versión.</p><div data-history></div></section></aside></div>`;
  document.body.append(panel);
  const q=k=>panel.querySelector('[data-'+k+']');q('name').textContent=frame.name;q('prompt').value=imageLabDefaultPrompt;
  q('base').parentElement.insertAdjacentHTML('afterend','<div class="ar-base-preview" style="display:flex;align-items:center;gap:10px;margin:8px 0"><img data-base-preview alt="Base elegida para generar" style="width:48px;height:48px;object-fit:contain;background:#292929"><small data-base-label></small></div>');
  const alphaChoice=document.createElement('label');
  alphaChoice.innerHTML='Transparencia<select data-alpha-mode aria-label="Transparencia de la nueva versión"><option value="none">Alpha después · conservar fondo</option><option value="ai">Extraer alpha con ImageLab</option></select>';
  q('ai-options').append(alphaChoice);
  q('alpha-mode').onchange=modelChanged;
  const sidebar=panel.querySelector('.ar-sidebar'),generateSection=panel.querySelector('.ar-generate'),versionsSection=panel.querySelector('.ar-versions');
  const sidebarTabs=document.createElement('div');sidebarTabs.className='ar-sidebar-tabs';sidebarTabs.setAttribute('role','tablist');sidebarTabs.setAttribute('aria-label','Panel del asset');
  const versionTab=ReviewUI.button('Versiones','layers',()=>showSidebar('versions')),
    generateTab=ReviewUI.button('Generar con Wonder ×4 → Bria · desde original · consume créditos','wand-sparkles',()=>generateWonder()),
    advancedTab=ReviewUI.button('Avanzado','sliders-horizontal',()=>showSidebar('generate'));
  for(const [button,label] of [[versionTab,'Versiones'],[generateTab,'Generar'],[advancedTab,'Avanzado']]){button.className='';button.append(document.createTextNode(label));sidebarTabs.append(button);}
  sidebarTabs.removeAttribute('role');
  const quickGenerationStatus=document.createElement('p');quickGenerationStatus.className='ar-quick-generation-status';quickGenerationStatus.setAttribute('role','status');quickGenerationStatus.textContent='Generar: Wonder ×4 → Bria · créditos';
  sidebar.prepend(sidebarTabs,quickGenerationStatus);
  function showSidebar(view){generateSection.hidden=view!=='generate';versionsSection.hidden=view!=='versions';versionTab.setAttribute('aria-pressed',String(view==='versions'));advancedTab.setAttribute('aria-pressed',String(view==='generate'));sidebar.scrollTop=0;}
  showSidebar('versions');
  const techniqueLabel=document.createElement('label');techniqueLabel.innerHTML='1 · Técnica<select data-generation-technique aria-label="Técnica de generación"><option value="upscale">Escalar el original</option><option value="ai">Redibujar con prompt</option></select>';
  q('model').parentElement.before(techniqueLabel);q('model').parentElement.firstChild.textContent='Motor y modelo';
  const modelDescription=document.createElement('p');modelDescription.className='ar-model-description';q('model').parentElement.after(modelDescription);
  const modelOptions=[...q('model').options].map(option=>({value:option.value,label:option.textContent})),chosenModels={upscale:q('model').value,ai:''};let imageLabConnection='Conectando…',generating=false;
  function renderModels(){const technique=q('generation-technique').value;const options=modelOptions.filter(o=>o.value.startsWith('ai:')===(technique==='ai'));q('model').replaceChildren(...options.map(o=>new Option(o.label,o.value)));if(options.some(o=>o.value===chosenModels[technique]))q('model').value=chosenModels[technique];q('model').disabled=!options.length;q('generate').disabled=generating||!options.length;modelChanged();updateBasePreview();}
  q('generation-technique').onchange=renderModels;
  q('base').parentElement.firstChild.textContent='2 · Imagen que se modifica';
  const basePreview=q('base-preview').parentElement;basePreview.className='ar-reference-card is-base';basePreview.removeAttribute('style');q('base-preview').removeAttribute('style');
  const baseCaption=document.createElement('span');baseCaption.innerHTML='<strong>BASE · para editar</strong>';baseCaption.append(q('base-label'));basePreview.append(baseCaption);
  const referenceCard=document.createElement('div');referenceCard.className='ar-reference-card is-reference';
  referenceCard.innerHTML='<img alt="Referencia fija: original del juego"><span><strong>REFERENCIA · original</strong><small>Guía de pose, paleta y grosor de línea. No se usa otro asset.</small></span>';
  referenceCard.querySelector('img').src='/api/reference?id='+frame.id;basePreview.after(referenceCard);
  const scaleReference=referenceCard.cloneNode(true);scaleReference.className='ar-reference-card';scaleReference.querySelector('strong').textContent='BASE · original del juego';scaleReference.querySelector('small').textContent='Escala desde el original. No usa otra versión ni un prompt.';q('ai-options').before(scaleReference);
  q('prompt').parentElement.firstChild.textContent='3 · Tu instrucción';q('alpha-mode').parentElement.firstChild.textContent='4 · Transparencia';
  function updateBasePreview(){
    const key=q('base').value,v=versions.find(v=>v.key===key);
    q('base-preview').src=key==='original'?'/api/reference?id='+frame.id:v?.url||'';
    q('base-label').textContent=q('base').selectedOptions[0]?.textContent||'Original';
    referenceCard.querySelector('small').textContent=key==='original'?'El mismo original guía pose, paleta y trazo. No se agrega otro asset.':'Guía de pose, paleta y grosor de línea; la imagen azul es la que se modifica.';
    for(const b of q('history').querySelectorAll('.ar-version')){const badge=b.querySelector('[data-base-badge]');if(badge)badge.remove();if(b.dataset.key===key&&q('model').value.startsWith('ai:')){const tag=document.createElement('small');tag.dataset.baseBadge='';tag.textContent='BASE PARA GENERAR';tag.style.color='#73adff';b.querySelector('span').append(tag);}}
  }
  q('base').onchange=()=>{const v=versions.find(v=>v.key===q('base').value);if(v)showVersion(v.key);updateBasePreview();};
  const toolbox=ReviewUI.tools(panel.querySelector('.ar-bottom'),runTechnique);toolbox.setDisabled(true);
  const importZone=document.createElement('div');importZone.className='ar-import-zone';
  const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='image/png,.png';fileInput.multiple=true;fileInput.hidden=true;fileInput.setAttribute('aria-label','Archivos PNG para nuevas versiones');
  const importButton=ReviewUI.button('Subir versiones PNG','upload',()=>fileInput.click(),'ar-upload-button');importButton.append(document.createTextNode('Subir PNG'));importButton.disabled=true;
  const importHint=document.createElement('small');importHint.textContent='O arrastrá archivos hasta acá';importZone.append(importButton,importHint,fileInput);q('history').before(importZone);
  fileInput.onchange=()=>{importFiles([...fileInput.files]);fileInput.value='';};
  panel.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy';importZone.classList.add('is-dragging');}});
  panel.addEventListener('dragleave',e=>{if(!panel.contains(e.relatedTarget))importZone.classList.remove('is-dragging');});
  panel.addEventListener('drop',e=>{if(!e.dataTransfer.files.length)return;e.preventDefault();e.stopPropagation();importZone.classList.remove('is-dragging');importFiles([...e.dataTransfer.files]);});
  let jobs=[],versions=[],selected=null,info=null,timer=null,signature='',busy=false,zoom=1,px=0,py=0,drag=null,closed=false,refreshSerial=0,actionMessage='';
  const review={panel,close(){closed=true;clearTimeout(timer);panel.remove();if(assetReview===review)assetReview=null;try{sessionStorage.removeItem('monkey-review-route');const url=new URL(location.href);url.searchParams.delete('asset');url.searchParams.delete('version');window.history.replaceState(null,'',url);}catch{};document.title='Monkey · Assets';assetGrid.open().catch(error=>message(error.message,true));}};assetReview=review;
  document.title=frame.name+' · Monkey';
  q('back').onclick=review.close;
  q('original').src='/api/reference?id='+frame.id;
  q('original').onerror=()=>{q('original-size').textContent='Original no disponible';};
  q('original').onload=()=>{q('original-size').textContent=q('original').naturalWidth+' × '+q('original').naturalHeight;};
  q('result').onload=()=>{q('result-size').textContent=q('result').naturalWidth+' × '+q('result').naturalHeight;};
  q('result').onerror=()=>{q('status').textContent='No se pudo cargar esta versión. Se conserva en el historial.';};
  function transform(){for(const img of panel.querySelectorAll('.ar-image-area img'))img.style.transform=`translate(${px}px,${py}px) scale(${zoom})`;q('zoom').textContent=Math.round(zoom*100)+'%';}
  function scale(factor){zoom=Math.max(.25,Math.min(12,zoom*factor));transform();}
  q('fit').onclick=()=>{zoom=1;px=py=0;transform();};q('minus').onclick=()=>scale(1/1.25);q('plus').onclick=()=>scale(1.25);
  for(const area of panel.querySelectorAll('.ar-image-area')){
    area.onwheel=e=>{e.preventDefault();scale(Math.exp(-e.deltaY*.002));};
    area.style.userSelect='none';area.style.webkitUserSelect='none';
    area.ondragstart=e=>e.preventDefault();
    area.onselectstart=e=>e.preventDefault();
    area.onpointerdown=e=>{
      if(e.button!==0||drag)return;
      e.preventDefault();
      drag={id:e.pointerId,x:e.clientX,y:e.clientY};
      area.setPointerCapture(e.pointerId);area.style.cursor='grabbing';
    };
    area.onpointermove=e=>{
      if(!drag||drag.id!==e.pointerId)return;
      e.preventDefault();px+=e.clientX-drag.x;py+=e.clientY-drag.y;
      drag.x=e.clientX;drag.y=e.clientY;transform();
    };
    const endPan=e=>{
      if(!drag||drag.id!==e.pointerId)return;
      drag=null;area.style.cursor='grab';
      if(area.hasPointerCapture(e.pointerId))area.releasePointerCapture(e.pointerId);
    };
    area.onpointerup=area.onpointercancel=area.onlostpointercapture=endPan;
  }
  q('background').onchange=()=>{for(const area of panel.querySelectorAll('.ar-image-area')){area.style.background=q('background').value==='checker'?'':q('background').value;}};
  function jobStatus(job){return job?.status==='running'?({wonder:'1/2 · Escalando con Wonder',matting:'2/2 · Topaz extrayendo transparencia', 'bria-alpha':job.operation==='refine-alpha'?'Extrayendo alpha con Bria':'2/2 · Bria extrayendo transparencia','extracting-alpha':'Extrayendo alpha'}[job.stage]||'Procesando'):job?.alpha_mode==='none'&&['ready','applied'].includes(job.status)?'Dibujo listo · alpha pendiente':imageLabStates[job?.status]||'Sin imagen';}
  function selectedVersion(){return versions.find(v=>v.key===selected);}
  function isCurrent(v){return v.kind==='current'||!!(v.job?.candidate_sha256&&v.job.candidate_sha256===info.current_sha256&&(!info.selected_variant||info.selected_variant.job_id===v.job.id));}
  function showVersion(key,chooseBase=false){
    selected=key;const v=selectedVersion();if(!v)return;
    if(chooseBase&&v.url&&[...q('base').options].some(o=>o.value===key)){q('base').value=key;updateBasePreview();}
    if(!closed){try{sessionStorage.setItem('monkey-review-route',JSON.stringify({asset:frame.id,version:key}));const url=new URL(location.href);url.searchParams.set('asset',frame.id);url.searchParams.set('version',key);window.history.replaceState(null,'',url);}catch{}}
    q('version-title').textContent=v.label;q('result').hidden=!v.url;q('empty').hidden=!!v.url;
    if(v.url){if(q('result').getAttribute('src')!==v.url)q('result').src=v.url;}else{q('result').removeAttribute('src');q('result-size').textContent='';q('empty').textContent=v.job?.error||jobStatus(v.job)||'Sin imagen';}
    q('status').textContent=actionMessage||v.job?.error||(isCurrent(v)?'✓ Esta versión está en uso.':v.job?.quality?.passed===false?'Aviso automático: '+v.job.quality.issues.join(', ')+'. Podés elegir usarla igualmente.':v.job?jobStatus(v.job)+' · '+v.job.model:'Guardado anterior. Restaurarlo conserva también tu versión actual.');
    q('use').disabled=busy||!v.url||isCurrent(v);
    q('use').textContent=busy?'Procesando…':isCurrent(v)?'✓ Versión en uso':'Usar esta versión';
    q('manual').disabled=busy||!v.url;
    toolbox.setDisabled(busy||!v.url);importButton.disabled=busy||!info;
    q('layer').disabled=busy||!v.url||v.kind==='current';
    if(v.job&&v.job.id===lastToolJob){toolbox.feedback(v.job.error||(['ready','applied'].includes(v.job.status)?'Nueva versión lista para revisar.':jobStatus(v.job)),v.job.error?'error':['ready','applied'].includes(v.job.status)?'good':'running');}
    for(const button of q('history').querySelectorAll('.ar-version'))button.setAttribute('aria-pressed',String(button.dataset.key===key));
  }
  function renderHistory(history){
    versions=[{key:'current',kind:'current',label:'En uso',url:info.image}];
    for(const job of jobs)versions.push({key:job.id,kind:'job',label:job.model+(job.operation==='alpha-only'?' · Alpha':''),job,url:job.image});
    for(const name of history.items)versions.push({key:name,kind:'save',label:'Guardado · '+new Date(Number(name.split('-')[0])/1e6).toLocaleString(),url:'/api/version?id='+frame.id+'&name='+name});
    q('history').replaceChildren();q('count').textContent=versions.length;
    importHint.textContent='Soltá PNG · '+info.width+' × '+info.height+' px';
    for(const v of versions){const b=document.createElement('button');b.className='ar-version';b.dataset.key=v.key;b.setAttribute('aria-label','Comparar '+v.label+(v.job?' · '+v.job.id.slice(-6):''));b.setAttribute('aria-pressed','false');
      if(v.url){const img=document.createElement('img');img.src=v.url;img.loading='lazy';img.alt='';b.append(img);}
      const text=document.createElement('span'),title=document.createElement('strong'),meta=document.createElement('small');title.textContent=v.label;
      const current=isCurrent(v);b.dataset.current=String(!!current);
      b.dataset.state=v.job?.error||v.job?.quality?.passed===false?'error':['queued','running'].includes(v.job?.status)?'running':current?'good':'pending';
      meta.textContent=v.job?(current?'✓ EN USO':v.job.quality?.passed===false?'Con alertas':v.job.status==='applied'?'Usada anteriormente':jobStatus(v.job))+' · '+new Date(v.job.created_at*1000).toLocaleTimeString():v.kind==='current'?(info.selected_variant?.model||'Último guardado manual'):'Edición conservada';text.append(title,meta);b.append(text);b.onclick=()=>{if(busy)return;actionMessage='';toolbox.feedback('');showVersion(v.key,true);};
      const row=document.createElement('div');row.className='ar-version-item';row.append(b);
      if(v.url){const actions=document.createElement('div');actions.className='ar-version-transfers';for(const [action,label,icon] of [['download','Descargar PNG','download'],['copy','Copiar imagen','copy']]){const button=ReviewUI.button(label+' · '+v.label,icon,()=>transferVersion(action,v,button));actions.append(button);}row.append(actions);}
      q('history').append(row);}
    const base=q('base').value;q('base').replaceChildren(new Option('Original','original'));
    for(const v of versions.filter(v=>v.url))q('base').add(new Option(v.label+(v.job?' · '+new Date(v.job.created_at*1000).toLocaleTimeString()+' · '+v.key.slice(-6):''),v.key));
    if([...q('base').options].some(o=>o.value===base))q('base').value=base;
    if(!versions.some(v=>v.key===selected))selected=initialJob&&versions.some(v=>v.key===initialJob)?initialJob:info.revision?'current':jobs.find(j=>j.image)?.id||'current';
    showVersion(selected);updateBasePreview();
  }
  async function refresh(force=false){
    clearTimeout(timer);if(closed)return;if(busy&&!force){timer=setTimeout(refresh,2500);return;}
    const serial=++refreshSerial;
    try{
      const [result,history,current]=await Promise.all([api('/api/imagelab/jobs?asset='+frame.id),api('/api/history?id='+frame.id),api('/api/open?id='+frame.id)]);
      if(closed||serial!==refreshSerial)return;jobs=result.jobs;info=current;
      const next=JSON.stringify([jobs,history,info.revision]);
      q('summary').textContent=jobs.filter(j=>['queued','running'].includes(j.status)).length+' en cola · '+jobs.filter(j=>j.image).length+' resultados';
      if(force||next!==signature){signature=next;renderHistory(history);}
    }catch(error){q('message').textContent=error.message;}
    if(!closed)timer=setTimeout(refresh,2500);
  }
  function modelChanged(){const ai=q('generation-technique').value==='ai';q('ai-options').hidden=!ai;scaleReference.hidden=ai;modelDescription.textContent=ai?'Motor: ImageLab / '+(q('model').selectedOptions[0]?.textContent||imageLabConnection):q('model').value.includes('Wonder')?'Motor: Topaz directo + Bria en Replicate':'Motor: Replicate / '+(q('model').selectedOptions[0]?.textContent||'');q('recipe').textContent=q('model').value.includes('Wonder 3.5')?'Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.':ai?(q('alpha-mode').value==='none'?'Base + tu prompt → dibujo con fondo. Una generación ImageLab; la transparencia la resolvés después.':'Base + tu prompt → dibujo → extracción de alpha. Son dos llamadas a ImageLab.'):'Original → escalado ×4. Cada envío crea una variante y consume Replicate.';}
  q('model').onchange=()=>{chosenModels[q('generation-technique').value]=q('model').value;modelChanged();updateBasePreview();};
  let lastToolJob=null;
  function sourceOf(v){return {id:frame.id,revision:info.revision,...(v.kind==='job'?{job_id:v.job.id}:v.kind==='save'?{history:v.key}:{})};}
  async function runTechnique(technique){
    const v=selectedVersion();if(busy||!v?.url)return;
    busy=true;actionMessage='';toolbox.feedback('Agregando a la cola…','running');showVersion(selected);
    try{
      const ai=['imagelab','bria'].includes(technique),settings=toolbox.settings();
      const job=ai?await api('/api/variants/extract-alpha',{...sourceOf(v),engine:technique,...(technique==='imagelab'&&q('model').value.startsWith('ai:')?{model:q('model').value.slice(3)}:{})}):await api('/api/variants/refine-alpha',{
        ...sourceOf(v),...settings,trim_pixels:technique==='trim'?settings.trim_pixels:0,tint_strength:technique==='tint'?settings.tint_strength:0,
        remove_magenta:technique==='magenta',outline:['white-2','red-4'].includes(technique)?technique:null,
        protect_seams:technique==='magenta'?false:settings.protect_seams});
      selected=job.id;lastToolJob=job.id;showSidebar('versions');toolbox.feedback(ai?'Alpha en cola · el dibujo se conserva.':'En cola · proceso local, sin créditos.','running');await refresh(true);
    }catch(error){actionMessage=error.message;toolbox.feedback(error.message,'error');}finally{busy=false;showVersion(selected);}
  }
  async function transferVersion(action,v,button){
    button.disabled=true;
    try{if(action==='copy')await ReviewUI.copy(v.url);else await ReviewUI.download(v.url,frame.name+'--'+v.key.replace(/[^a-zA-Z0-9_-]/g,'_')+'.png');toolbox.feedback(action==='copy'?'Imagen copiada al portapapeles.':'PNG descargado.','good');}
    catch(error){toolbox.feedback(action==='copy'?'No se pudo copiar la imagen. Usá Descargar PNG o habilitá el portapapeles del navegador.':error.message,'error');}
    finally{button.disabled=false;}
  }
  async function importFiles(files){
    if(busy||!info||!files.length)return;
    if(files.length>16){toolbox.feedback('Importá hasta 16 PNG por vez.','error');return;}
    busy=true;showVersion(selected);let imported=0;const errors=[];
    for(const file of files){
      try{
        if(!/\.png$/i.test(file.name)||file.size>32*1024*1024)throw new Error('Usá PNG de hasta 32 MB.');
        toolbox.feedback('Importando '+file.name+'…','running');
        const job=await api('/api/variants/import',{id:frame.id,name:file.name,png:await ReviewUI.dataURL(file)});selected=job.id;imported++;
      }catch(error){errors.push(file.name+': '+error.message);}
    }
    if(imported)showSidebar('versions');await refresh(true);busy=false;showVersion(selected);
    toolbox.feedback((imported?imported+' versión(es) importada(s). ':'')+errors.join(' '),errors.length?'error':'good');
  }
  q('generate').onclick=async()=>{
    if(generating||!q('model').value)return;generating=true;generateTab.disabled=true;q('generate').disabled=true;q('message').textContent='Agregando a la cola…';
    try{const value=q('model').value,base=q('base').value,v=versions.find(v=>v.key===base);const source=base==='original'?{}:v?.kind==='current'?{base_kind:'current',base_revision:info.revision}:v?.kind==='save'?{base_kind:'history',base_history:v.key}:{upscale_job_id:base};const job=!value.startsWith('ai:')?await api('/api/upscale/jobs',{id:frame.id,enhance_model:value.slice(value.indexOf(':')+1)}):await api('/api/imagelab/jobs',{id:frame.id,model:value.slice(3),prompt:q('prompt').value,preserve_alpha:q('alpha-mode').value!=='none',alpha_mode:q('alpha-mode').value,style_id:'',...source});
      selected=job.id;lastToolJob=job.id;showSidebar('versions');await refresh(true);q('message').textContent='En cola. Podés probar otro modelo o volver a la grilla.';
    }catch(error){q('message').textContent=error.message;}finally{generating=false;generateTab.disabled=false;q('generate').disabled=!q('model').value;}
  };
  async function generateWonder(){
    if(generating)return;generating=true;generateTab.disabled=true;q('generate').disabled=true;
    quickGenerationStatus.textContent='Encolando Wonder ×4 → Bria…';quickGenerationStatus.dataset.state='running';
    try{
      const job=await api('/api/upscale/jobs',{id:frame.id,enhance_model:'Wonder 3.5 High + Bria'});
      selected=job.id;lastToolJob=job.id;showSidebar('versions');await refresh(true);
      quickGenerationStatus.textContent='Wonder ×4 → Bria en cola. Resultado en Versiones.';quickGenerationStatus.dataset.state='pending';
    }catch(error){quickGenerationStatus.textContent=error.message;quickGenerationStatus.dataset.state='error';}
    finally{generating=false;generateTab.disabled=false;q('generate').disabled=!q('model').value;}
  }
  async function useSelected(forEdit=false){
    const v=selectedVersion();if(!v||!v.url)throw new Error('Elegí una versión terminada.');
    ++refreshSerial;clearTimeout(timer);
    // Keep the revision observed in this review: another writer must not be overwritten.
    let result;
    if(v.kind==='job')result=await api('/api/variants/select',{job_id:v.job.id,revision:info.revision,for_edit:forEdit});
    else if(v.kind==='save')result=await api('/api/restore',{id:frame.id,name:v.key,revision:info.revision});
    if(result)info.revision=result.revision;
    cache.delete(frame.id);frame.edited=true;frame.revision=info.revision;selected='current';await refresh(true);
  }
  q('use').onclick=async()=>{if(busy)return;busy=true;actionMessage='Aplicando la versión seleccionada…';showVersion(selected);try{await useSelected();actionMessage='✓ Versión en uso. La anterior quedó en el historial.';}catch(error){actionMessage=error.message;await refresh(true);}finally{busy=false;showVersion(selected);}};
  q('layer').onclick=()=>openManual(true);
  q('manual').onclick=()=>openManual(false);
  async function openManual(asLayer){
    if(busy)return;busy=true;actionMessage='Abriendo la versión seleccionada…';showVersion(selected);
    try{
      let hiddenLayers;
      if(asLayer){
        const variant=selectedVersion();
        const response=await fetch(variant.url);if(!response.ok)throw new Error('No se pudo cargar la versión.');
        const blob=await response.blob();
        const png=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
        hiddenLayers=[{png,name:'Versión · '+variant.label}];
      }
      await save();if(!asLayer)await useSelected(true);
      const sequence=state.groups.find(g=>g[0].group===frame.group);if(!sequence)throw new Error('No se encontró la secuencia.');
      state.busy=false;await navigate(sequence.findIndex(f=>f.id===frame.id),sequence);
      if(state.info?.frame.id!==frame.id)throw new Error('No se pudo cargar el asset.');
      await confiteButton.onclick({hiddenLayers});if(!confiteSession)throw new Error('No se pudo abrir Confite.');
      panel.hidden=true;const grid=document.querySelector('.asset-browser');if(grid)grid.hidden=true;
      confiteSession.overlay.querySelector('[data-close]').textContent='Guardar y volver a comparación';
      confiteSession.onReviewReturn=()=>{if(closed)return;panel.hidden=false;selected='current';refresh(true);};
    }catch(error){actionMessage=error.message;await refresh(true);}finally{busy=false;if(panel.hidden)actionMessage='';showVersion(selected);}
  };
  await refresh(true);
  // Availability of the generator never blocks viewing local results.
  modelChanged();
  api('/api/imagelab/status').then(connection=>{if(closed)return;imageLabConnection=connection.error||'Sin modelos disponibles';if(connection.ready){for(const model of connection.models||[])modelOptions.push({value:'ai:'+model,label:model});chosenModels.ai='ai:'+(connection.defaultModel||connection.models[0]);}renderModels();}).catch(error=>{if(!closed){imageLabConnection=error.message;renderModels();}});
}







