'use strict';
// One review surface per asset. Selecting a version only changes the preview.
let assetReview=null;
async function openAssetReview(frame, initialJob=null, initialInfo=null, options={}){
  if(assetReview){assetReview.close(false);}
  const embedded=!!options.embedded,grid=document.querySelector('.asset-browser');
  const previousTitle=document.title,previousFocus=document.activeElement;
  const shade=embedded?document.createElement('div'):null;
  if(shade){shade.className='ar-review-shade';shade.setAttribute('aria-hidden','true');document.body.append(shade);}
  const panel=document.createElement('section');panel.className='ar-workspace';panel.setAttribute('aria-label','Comparación de asset');
  panel.innerHTML=`<header class="ar-header"><button data-back>Assets</button><div><small>COMPARAR Y REFINAR</small><h1 data-name></h1></div><span data-summary></span></header>
  <div class="ar-layout"><main class="ar-main"><div class="ar-toolbar"><span>Vista sincronizada</span><button data-fit>Ajustar</button><button data-minus aria-label="Alejar comparación">−</button><output data-zoom>100%</output><button data-plus aria-label="Acercar comparación">+</button><select data-background aria-label="Fondo de comparación"><option value="checker">Transparencia</option><option value="#999da3">Gris</option><option value="#fafafa">Blanco</option><option value="#17191d">Oscuro</option><option value="#ff00ff">Magenta</option></select></div>
  <div class="ar-canvases"><figure><figcaption><strong>Original</strong><span data-original-size></span></figcaption><div class="ar-image-area"><img data-original alt="Original del juego" draggable="false"></div></figure><figure><figcaption><strong data-version-title>Resultado</strong><span data-result-size></span></figcaption><div class="ar-image-area"><img data-result alt="Versión seleccionada" draggable="false"><p data-empty hidden></p></div></figure></div>
  <div class="ar-bottom"><p data-status role="status"></p><div class="ar-version-actions"><button data-use>Usar esta versión</button><button data-layer>Enviar como capa a Confite</button><button data-manual class="accent">Retocar en Confite</button></div></div></main>
  <aside class="ar-sidebar"><section class="ar-generate"><h2>Crear otra versión</h2><label>Modelo<select data-model aria-label="Modelo para nueva versión"><optgroup label="Topaz · API directa"><option value="upscale:Wonder 3.5 High + Bria">Wonder 3.5 High ×4 + Bria</option></optgroup><optgroup label="Escalado · Replicate"><option value="upscale:Real-ESRGAN Anime 6B">Real-ESRGAN · Anime 6B ×4</option><option value="topaz:CGI">Topaz · CGI</option><option value="topaz:High Fidelity V2">Topaz · Alta fidelidad</option><option value="topaz:Standard V2">Topaz · Estándar</option><option value="topaz:Low Resolution V2">Topaz · Baja resolución</option></optgroup></select></label><div data-ai-options hidden><label>Base<select data-base aria-label="Base para ImageLab"><option value="original">Original</option></select></label><label>Instrucciones<textarea data-prompt rows="3"></textarea></label></div><p data-recipe>Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.</p><button data-generate class="accent">Generar versión</button><p data-message role="status"></p></section>
  <section class="ar-versions"><div class="ar-section-title"><h2>Versiones</h2><span data-count></span></div><p class="ar-layers-loading" data-loading role="status">Cargando versiones…</p><div data-history class="ar-layers-list"></div></section></aside></div>`;
  document.body.append(panel);
  if(embedded){panel.classList.add('ar-modal');panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.tabIndex=-1;if(grid)grid.inert=true;panel.focus();}
  else assetGrid.hide();
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
  function showSidebar(view){generateSection.hidden=view!=='generate';versionsSection.hidden=view!=='versions';versionTab.setAttribute('aria-pressed',String(view==='versions'));advancedTab.setAttribute('aria-pressed',String(view==='generate'));sidebar.scrollTop=0;if(view==='generate')loadGenerator();}
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
    q('base-preview').src=key==='original'?'/api/source-image?id='+frame.id+(info?.source_preparation?'&v='+info.source_preparation.revision:''):v?.url||'';
    q('base-label').textContent=q('base').selectedOptions[0]?.textContent||'Original';
    referenceCard.querySelector('small').textContent=key==='original'?'El mismo original guía pose, paleta y trazo. No se agrega otro asset.':'Guía de pose, paleta y grosor de línea; la imagen azul es la que se modifica.';
    for(const b of q('history').querySelectorAll('.ar-layer')){const badge=b.querySelector('[data-base-badge]');if(badge)badge.remove();if(b.dataset.key===key&&q('model').value.startsWith('ai:')){const tag=document.createElement('small');tag.dataset.baseBadge='';tag.className='ar-layer-meta';tag.textContent='BASE PARA GENERAR';tag.style.color='#73adff';b.querySelector('.ar-layer-text').append(tag);}}
  }
  q('base').onchange=()=>{const v=versions.find(v=>v.key===q('base').value);if(v)showVersion(v.key);updateBasePreview();};
  const toolbox=ReviewUI.tools(panel.querySelector('.ar-bottom'),runTechnique,()=>{const v=selectedVersion();return v?sourceOf(v):{id:frame.id};});toolbox.setDisabled(true);
  let previewObjUrl=null;
  toolbox.section.addEventListener('preview-update',e=>{
    if(previewObjUrl)URL.revokeObjectURL(previewObjUrl);
    previewObjUrl=e.detail.url;
    if(previewObjUrl){q('result').src=previewObjUrl;q('version-title').textContent='Preview';q('status').textContent='Ajustá los parámetros y pulsá OK para guardar.';}
    else{const v=selectedVersion();if(v)showVersion(v.key);}
  });
  const importZone=document.createElement('div');importZone.className='ar-import-zone';
  const fileInput=document.createElement('input');fileInput.type='file';fileInput.accept='image/png,.png';fileInput.multiple=true;fileInput.hidden=true;fileInput.setAttribute('aria-label','Archivos PNG para nuevas versiones');
  const importButton=ReviewUI.button('Subir versiones PNG','upload',()=>fileInput.click(),'ar-upload-button');importButton.append(document.createTextNode('Subir PNG'));importButton.disabled=true;
  const importHint=document.createElement('small');importHint.textContent='O arrastrá archivos hasta acá';importZone.append(importButton,importHint,fileInput);q('history').before(importZone);
  fileInput.onchange=()=>{importFiles([...fileInput.files]);fileInput.value='';};
  panel.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy';importZone.classList.add('is-dragging');}});
  panel.addEventListener('dragleave',e=>{if(!panel.contains(e.relatedTarget))importZone.classList.remove('is-dragging');});
  panel.addEventListener('drop',e=>{if(!e.dataTransfer.files.length)return;e.preventDefault();e.stopPropagation();importZone.classList.remove('is-dragging');importFiles([...e.dataTransfer.files]);});
  let jobs=[],versions=[],selected=null,info=null,timer=null,signature='',busy=false,zoom=1,px=0,py=0,drag=null,closed=false,refreshSerial=0,actionMessage='',historyItems=[];
  const onVisibility=()=>{clearTimeout(timer);if(!document.hidden&&!closed)refresh(true);};
  document.addEventListener('visibilitychange',onVisibility);
  const review={panel,close(returnToAssets=true){closed=true;clearTimeout(timer);document.removeEventListener('visibilitychange',onVisibility);panel.remove();shade?.remove();if(assetReview===review)assetReview=null;if(embedded){if(grid){grid.inert=false;grid.hidden=false;}document.title=previousTitle;if(returnToAssets){options.onClose?.();if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});}return;}try{sessionStorage.removeItem('monkey-review-route');const url=new URL(location.href);url.searchParams.delete('asset');url.searchParams.delete('version');window.history.replaceState(null,'',url);}catch{};document.title='Monkey · Assets';if(returnToAssets)assetGrid.open().catch(error=>message(error.message,true));}};assetReview=review;
  document.title=frame.name+' · Monkey';
  q('back').onclick=()=>review.close();
  let previousButton,nextButton;
  if(embedded){
    q('back').replaceChildren(ReviewUI.icon('x'),document.createTextNode('Cerrar'));q('back').setAttribute('aria-label','Cerrar comparación y volver al listado');
    const navigation=document.createElement('nav');navigation.className='ar-review-navigation';navigation.setAttribute('aria-label','Recorrer assets del listado');
    const ids=options.ids||[frame.id],position=ids.indexOf(frame.id),counter=document.createElement('span');counter.textContent=(position+1)+' / '+ids.length;
    const step=delta=>{if(!busy&&ids[position+delta])options.navigate?.(ids[position+delta]);};
    previousButton=ReviewUI.button('Asset anterior','chevron-left',()=>step(-1));nextButton=ReviewUI.button('Asset siguiente','chevron-right',()=>step(1));
    previousButton.disabled=position<=0;nextButton.disabled=position<0||position>=ids.length-1;navigation.append(previousButton,counter,nextButton);panel.querySelector('.ar-header').append(navigation);
    panel.addEventListener('keydown',e=>{
      e.stopPropagation();
      if(e.key==='Escape'){e.preventDefault();if(!busy)review.close();return;}
      if(e.key==='Tab'){const controls=[...panel.querySelectorAll('button,input,select,textarea,a[href],[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length);const first=controls[0],last=controls.at(-1);if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel)){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}return;}
      if(!e.target.closest('input,textarea,select,[contenteditable=true]')&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();step(e.key==='ArrowLeft'?-1:1);}
    });
  }
  const approveButton=ReviewUI.button('Usar y aprobar esta versión','check',()=>approveSelected(),'ar-approve-version');approveButton.append(document.createTextNode('Usar y aprobar'));approveButton.disabled=true;q('use').after(approveButton);
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
    selected=key;const v=selectedVersion();if(!v){if(actionMessage)q('status').textContent=actionMessage;return;}
    if(chooseBase&&v.url&&[...q('base').options].some(o=>o.value===key)){q('base').value=key;updateBasePreview();}
    if(!closed&&!embedded){try{sessionStorage.setItem('monkey-review-route',JSON.stringify({asset:frame.id,version:key}));const url=new URL(location.href);url.searchParams.set('asset',frame.id);url.searchParams.set('version',key);window.history.replaceState(null,'',url);}catch{}}
    q('version-title').textContent=v.label;q('result').hidden=!v.url;q('empty').hidden=!!v.url;
    if(toolbox.isPreview()){/* preserve preview image */}
    else if(v.url){if(q('result').getAttribute('src')!==v.url)q('result').src=v.url;}else{q('result').removeAttribute('src');q('result-size').textContent='';q('empty').textContent=v.job?.error||jobStatus(v.job)||'Sin imagen';}
    if(!toolbox.isPreview())q('status').textContent=actionMessage||v.job?.error||(isCurrent(v)?'✓ Esta versión está en uso.':v.job?.quality?.passed===false?'Aviso automático: '+v.job.quality.issues.join(', ')+'. Podés elegir usarla igualmente.':v.job?jobStatus(v.job)+' · '+v.job.model:'Guardado anterior. Restaurarlo conserva también tu versión actual.');
    q('use').disabled=busy||!v.url||isCurrent(v);
    const approved=isCurrent(v)&&imageLabApprovals[frame.id]?.sha256===info.current_sha256;
    approveButton.disabled=busy||!v.url||approved;approveButton.dataset.approved=String(!!approved);approveButton.lastChild.textContent=approved?'Aprobado':'Usar y aprobar';
    if(previousButton){const position=options.ids.indexOf(frame.id);previousButton.disabled=busy||position<=0;nextButton.disabled=busy||position>=options.ids.length-1;}
    q('use').textContent=busy?'Procesando…':isCurrent(v)?'✓ Versión en uso':'Usar esta versión';
    q('manual').disabled=busy||!v.url;
    toolbox.setDisabled(busy||!v.url);importButton.disabled=busy||!info;
    q('layer').disabled=busy||!v.url||v.kind==='current';
    if(v.job&&v.job.id===lastToolJob){toolbox.feedback(v.job.error||(['ready','applied'].includes(v.job.status)?'Nueva versión lista para revisar.':jobStatus(v.job)),v.job.error?'error':['ready','applied'].includes(v.job.status)?'good':'running');}
    for(const el of q('history').querySelectorAll('.ar-layer'))el.setAttribute('aria-pressed',String(el.dataset.key===key));
  }
  function thumbUrl(v){
    if(v.kind==='job'&&v.job?.image)return '/api/version-thumb?kind=job&job='+v.job.id;
    if(v.kind==='save')return '/api/version-thumb?kind=history&id='+frame.id+'&name='+v.key;
    if(v.kind==='current')return '/api/version-thumb?kind=current&id='+frame.id;
    return v.url;
  }
  function renderHistory(history){
    versions=[{key:'current',kind:'current',label:'En uso',url:info.image}];
    for(const job of jobs)versions.push({key:job.id,kind:'job',label:job.model+(job.operation==='alpha-only'?' · Alpha':''),job,url:job.image});
    for(const name of history.items)versions.push({key:name,kind:'save',label:'Guardado · '+new Date(Number(name.split('-')[0])/1e6).toLocaleString(),url:'/api/version?id='+frame.id+'&name='+name});
    q('history').replaceChildren();q('count').textContent=versions.length;q('loading').hidden=true;
    importHint.textContent='Soltá PNG · '+info.width+' × '+info.height+' px';
    for(const v of versions){
      const current=isCurrent(v);
      const state=v.job?.error||v.job?.quality?.passed===false?'error':['queued','running'].includes(v.job?.status)?'running':current?'good':'pending';
      const row=document.createElement('div');row.className='ar-layer';row.dataset.key=v.key;row.dataset.state=state;row.dataset.current=String(!!current);row.setAttribute('aria-pressed','false');
      // Thumbnail
      const thumb=document.createElement('div');thumb.className='ar-layer-thumb';
      if(v.url){const img=document.createElement('img');img.src=thumbUrl(v);img.loading='lazy';img.alt='';thumb.append(img);}
      else{thumb.classList.add('ar-layer-empty');}
      // Text
      const text=document.createElement('div');text.className='ar-layer-text';
      const title=document.createElement('span');title.className='ar-layer-title';title.textContent=v.label;
      const meta=document.createElement('span');meta.className='ar-layer-meta';
      meta.textContent=v.job?(current?'✓ En uso':v.job.quality?.passed===false?'Alertas':v.job.status==='applied'?'Usada':jobStatus(v.job))+' · '+new Date(v.job.created_at*1000).toLocaleTimeString():v.kind==='current'?(info.selected_variant?.model||'Manual'):'Historial';
      text.append(title,meta);
      // Actions (inline, visible on hover)
      const acts=document.createElement('div');acts.className='ar-layer-actions';
      if(v.url){for(const [action,tip,icon] of [['copy','Copiar','copy'],['download','Descargar','download']]){const btn=ReviewUI.button(tip,icon,e=>{e.stopPropagation();transferVersion(action,v,btn);});acts.append(btn);}}
      if(v.kind!=='current'){const del=ReviewUI.button('Borrar','x',async e=>{e.stopPropagation();del.disabled=true;row.style.opacity='.3';try{if(v.kind==='job')await api('/api/imagelab/delete',{job_id:v.job.id});else await api('/api/delete-history',{id:frame.id,name:v.key});if(selected===v.key)selected='current';await refresh(true);}catch(err){toolbox.feedback(err.message,'error');del.disabled=false;row.style.opacity='';}});acts.append(del);}
      row.append(thumb,text,acts);
      row.onclick=()=>{if(busy)return;actionMessage='';toolbox.feedback('');showVersion(v.key,true);};
      q('history').append(row);
    }
    const base=q('base').value;q('base').replaceChildren(new Option('Original','original'));
    for(const v of versions.filter(v=>v.url))q('base').add(new Option(v.label+(v.job?' · '+new Date(v.job.created_at*1000).toLocaleTimeString()+' · '+v.key.slice(-6):''),v.key));
    if([...q('base').options].some(o=>o.value===base))q('base').value=base;
    if(!versions.some(v=>v.key===selected))selected=initialJob&&versions.some(v=>v.key===initialJob)?initialJob:info.revision?'current':jobs.find(j=>j.image)?.id||'current';
    showVersion(selected);updateBasePreview();
  }
  async function refresh(force=false){
    clearTimeout(timer);if(closed||document.hidden&&!force)return;if(busy&&!force){timer=setTimeout(refresh,2500);return;}
    const serial=++refreshSerial;
    try{
      const result=await api('/api/review?id='+frame.id),history=result.history;
      if(closed||serial!==refreshSerial)return;jobs=result.jobs;info=result.info;historyItems=history.items;
      SpriteBatches.ingest(jobs,{...imageLabApprovals,...result.approvals});if(result.approvals){if(result.approvals[frame.id])imageLabApprovals[frame.id]=result.approvals[frame.id];else delete imageLabApprovals[frame.id];}
      const preparation=info.source_preparation;
      sourceButton.lastChild.textContent=preparation?'Original preparado · '+preparation.colors.length+' colores excluidos':'Quitar colores del original';
      const sourceUrl='/api/source-image?id='+frame.id+(preparation?'&v='+preparation.revision:'');
      referenceCard.querySelector('img').src=sourceUrl;scaleReference.querySelector('img').src=sourceUrl;
      scaleReference.querySelector('strong').textContent=preparation?'BASE · original sin colores seleccionados':'BASE · original del juego';
      const next=JSON.stringify([jobs,historyItems,info.revision]);
      q('summary').textContent=jobs.filter(j=>['queued','running'].includes(j.status)).length+' en cola · '+jobs.filter(j=>j.image).length+' resultados';
      if(force||next!==signature){signature=next;renderHistory({items:historyItems});}
    }catch(error){q('message').textContent=error.message;}
    if(!closed&&!document.hidden)timer=setTimeout(refresh,10000);
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
      const ol=technique==='outline'?toolbox.outlineSettings():null;
      const job=ai?await api('/api/variants/extract-alpha',{...sourceOf(v),engine:technique,...(technique==='imagelab'&&q('model').value.startsWith('ai:')?{model:q('model').value.slice(3)}:{})}):await api('/api/variants/refine-alpha',{
        ...sourceOf(v),...settings,trim_pixels:technique==='trim'?settings.trim_pixels:0,tint_strength:technique==='tint'?settings.tint_strength:0,
        remove_magenta:technique==='magenta',outline:ol?'custom':null,outline_radius:ol?.radius,outline_color:ol?.color,
        alpha_original:technique==='alphaoriginal'||undefined,
        protect_seams:technique==='magenta'||technique==='alphaoriginal'?false:settings.protect_seams});
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
  async function approveSelected(){if(busy)return;busy=true;actionMessage='Aplicando y aprobando…';showVersion(selected);try{await useSelected();imageLabApprovals[frame.id]=await api('/api/imagelab/approve',{id:frame.id,revision:info.revision});await SequenceTools.refreshAssets([frame.id]);actionMessage='✓ Versión aplicada y aprobada.';}catch(error){actionMessage=error.message;}finally{busy=false;showVersion(selected);}}
  q('layer').onclick=()=>openManual(true);
  q('manual').onclick=()=>openManual(false);
  async function openManual(asLayer){
    if(busy)return;busy=true;actionMessage='Abriendo Confite…';showVersion(selected);
    try{
      // Wait for info if the initial review request hasn't finished yet.
      if(!info){actionMessage='Esperando datos del asset…';showVersion(selected);await refresh(true);if(!info)throw new Error('No se pudieron cargar los datos del asset.');}
      let hiddenLayers;
      if(asLayer){
        const variant=selectedVersion();
        if(!variant?.url)throw new Error('Elegí una versión con imagen.');
        const response=await fetch(variant.url);if(!response.ok)throw new Error('No se pudo cargar la versión.');
        const blob=await response.blob();
        const png=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
        hiddenLayers=[{png,name:'Versión · '+variant.label}];
      }
      await save();if(!asLayer&&selected!=='current')await useSelected(true);
      if(!state.catalogLoaded)await catalog();
      const sequence=state.groups.find(g=>g[0].group===frame.group);if(!sequence)throw new Error('No se encontró la secuencia.');
      state.busy=false;state.playing=false;state.pointer=null;await navigate(sequence.findIndex(f=>f.id===frame.id),sequence);
      if(state.info?.frame.id!==frame.id)throw new Error('No se pudo cargar el asset en el editor principal.');
      state.busy=false;state.pointer=null;
      await confiteButton.onclick({hiddenLayers});if(!confiteSession)throw new Error('No se pudo abrir Confite. Verificá que el asset esté cargado.');
      panel.hidden=true;if(shade)shade.hidden=true;const grid=document.querySelector('.asset-browser');if(grid)grid.hidden=true;
      confiteSession.overlay.querySelector('[data-close]').textContent='Guardar y volver a comparación';
      confiteSession.onReviewReturn=()=>{if(closed)return;panel.hidden=false;if(shade)shade.hidden=false;if(embedded&&grid)grid.hidden=false;selected='current';refresh(true);};
    }catch(error){actionMessage=error.message;await refresh(true);}finally{busy=false;if(panel.hidden)actionMessage='';showVersion(selected);}
  };
  // Show local/cached imagery before any history or provider request completes.
  const sourceButton=ReviewUI.button('Preparar original para generar sin agua','pipette',()=>SourcePreparation.open([frame],()=>refresh(true)),'ar-source-button');
  sourceButton.append(document.createTextNode('Quitar colores del original'));quickGenerationStatus.after(sourceButton);
  const cachedJob=(initialJob&&[imageLabAssetJobs.get(frame.id),imageLabResultJobs.get(frame.id)].find(j=>j?.id===initialJob))||null;
  q('result').src=cachedJob?.image||'/api/image?id='+frame.id+'&v='+(frame.revision||'base');
  q('version-title').textContent=cachedJob?.model||'En uso';
  q('use').disabled=q('manual').disabled=q('layer').disabled=true;toolbox.setDisabled(true);
  // Instant render: show cached jobs immediately so the version list appears without waiting for /api/review
  {
    const cachedJobs=LiveAssets.jobsFor(frame.id);
    if(cachedJobs.length||frame.edited){
      info={frame,image:'/api/image?id='+frame.id+'&v='+(frame.revision||'base'),width:frame.dimensions?.[0]||0,height:frame.dimensions?.[1]||0,revision:frame.revision,current_sha256:null,selected_variant:null,source_preparation:null};
      jobs=cachedJobs;
      q('loading').hidden=true;renderHistory({items:[]});
      q('status').textContent='Actualizando…';
    } else {
      q('status').textContent='Cargando versiones…';
    }
  }
  const onLive=event=>{if(!closed&&event.detail.ids.includes(frame.id)&&!busy)refresh(true);};
  const onPaste=async e=>{if(closed||busy)return;const item=[...e.clipboardData.items].find(i=>i.type==='image/png');if(!item)return;e.preventDefault();const file=item.getAsFile();if(!file)return;toolbox.feedback('Pegando versión…','running');try{const job=await api('/api/variants/import',{id:frame.id,name:'pasted.png',png:await ReviewUI.dataURL(file)});selected=job.id;showSidebar('versions');await refresh(true);toolbox.feedback('Versión pegada desde el portapapeles.','good');}catch(error){toolbox.feedback(error.message,'error');}};
  document.addEventListener('paste',onPaste);
  window.addEventListener('assets-live',onLive);const closeReview=review.close.bind(review);review.close=(...args)=>{document.removeEventListener('paste',onPaste);window.removeEventListener('assets-live',onLive);closeReview(...args);};
  refresh(true);
  // Availability of the generator never blocks viewing local results.
  modelChanged();
  let generatorLoaded=false;
  function loadGenerator(){if(generatorLoaded)return;generatorLoaded=true;
    api('/api/imagelab/status').then(connection=>{if(closed)return;imageLabConnection=connection.error||'Sin modelos disponibles';if(connection.ready){for(const model of connection.models||[])modelOptions.push({value:'ai:'+model,label:model});chosenModels.ai='ai:'+(connection.defaultModel||connection.models[0]);}renderModels();}).catch(error=>{if(!closed){imageLabConnection=error.message;renderModels();}});
  }
}







