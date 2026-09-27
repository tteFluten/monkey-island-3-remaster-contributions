'use strict';
// One review surface per asset. Selecting a version only changes the preview.
let assetReview=null;
async function openAssetReview(frame, initialJob=null){
  if(assetReview){assetReview.close();}
  const panel=document.createElement('section');panel.className='ar-workspace';panel.setAttribute('aria-label','Comparación de asset');
  panel.innerHTML=`<header class="ar-header"><button data-back>Assets</button><div><small>COMPARAR Y REFINAR</small><h1 data-name></h1></div><span data-summary></span></header>
  <div class="ar-layout"><main class="ar-main"><div class="ar-toolbar"><span>Vista sincronizada</span><button data-fit>Ajustar</button><button data-minus aria-label="Alejar comparación">−</button><output data-zoom>100%</output><button data-plus aria-label="Acercar comparación">+</button><select data-background aria-label="Fondo de comparación"><option value="checker">Transparencia</option><option value="#999da3">Gris</option><option value="#fafafa">Blanco</option><option value="#17191d">Oscuro</option><option value="#ff00ff">Magenta</option></select></div>
  <div class="ar-canvases"><figure><figcaption><strong>Original</strong><span data-original-size></span></figcaption><div class="ar-image-area"><img data-original alt="Original del juego" draggable="false"></div></figure><figure><figcaption><strong data-version-title>Resultado</strong><span data-result-size></span></figcaption><div class="ar-image-area"><img data-result alt="Versión seleccionada" draggable="false"><p data-empty hidden></p></div></figure></div>
  <div class="ar-bottom"><p data-status role="status"></p><button data-use>Usar esta versión</button><label>Comer borde <input data-trim type="number" min="0" max="3" step="0.25" value="0.5" aria-label="Píxeles a recortar del borde" style="width:60px"> px</label><label><input data-dark type="checkbox" checked> Proteger contorno oscuro</label><button data-refine-alpha title="Limpieza local del alpha: no genera imágenes ni consume créditos.">Limpiar borde · local</button><button data-layer>Enviar a Confite como capa oculta</button><button data-manual class="accent">Retocar esta versión en Confite</button></div></main>
  <aside class="ar-sidebar"><section class="ar-generate"><h2>Crear otra versión</h2><label>Modelo<select data-model aria-label="Modelo para nueva versión"><optgroup label="Topaz · API directa"><option value="upscale:Wonder 3.5 High + Bria">Wonder 3.5 High ×4 + Bria</option></optgroup><optgroup label="Escalado · Replicate"><option value="upscale:Real-ESRGAN Anime 6B">Real-ESRGAN · Anime 6B ×4</option><option value="topaz:CGI">Topaz · CGI</option><option value="topaz:High Fidelity V2">Topaz · Alta fidelidad</option><option value="topaz:Standard V2">Topaz · Estándar</option><option value="topaz:Low Resolution V2">Topaz · Baja resolución</option></optgroup></select></label><div data-ai-options hidden><label>Base<select data-base aria-label="Base para ImageLab"><option value="original">Original</option></select></label><label>Instrucciones<textarea data-prompt rows="3"></textarea></label></div><p data-recipe>Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.</p><button data-generate class="accent">Generar versión</button><p data-message role="status"></p></section>
  <section class="ar-versions"><div class="ar-section-title"><h2>Versiones</h2><span data-count></span></div><p class="ar-hint">Seleccioná para comparar. El trabajo actual solo cambia al usar o retocar una versión.</p><div data-history></div></section></aside></div>`;
  document.body.append(panel);
  const q=k=>panel.querySelector('[data-'+k+']');q('name').textContent=frame.name;q('prompt').value=imageLabDefaultPrompt;
  q('base').parentElement.insertAdjacentHTML('afterend','<div class="ar-base-preview" style="display:flex;align-items:center;gap:10px;margin:8px 0"><img data-base-preview alt="Base elegida para generar" style="width:48px;height:48px;object-fit:contain;background:#292929"><small data-base-label></small></div>');
  let baseInitialized=false;
  function updateBasePreview(){
    const key=q('base').value,v=versions.find(v=>v.key===key);
    q('base-preview').src=key==='original'?'/api/reference?id='+frame.id:v?.url||'';
    q('base-label').textContent='Base: '+(q('base').selectedOptions[0]?.textContent||'Original');
    for(const b of q('history').children){const badge=b.querySelector('[data-base-badge]');if(badge)badge.remove();if(b.dataset.key===key&&q('model').value.startsWith('ai:')){const tag=document.createElement('small');tag.dataset.baseBadge='';tag.textContent='BASE PARA GENERAR';tag.style.color='#73adff';b.querySelector('span').append(tag);}}
  }
  q('base').onchange=()=>{const v=versions.find(v=>v.key===q('base').value);if(v)showVersion(v.key);updateBasePreview();};
  q('refine-alpha').insertAdjacentHTML('beforebegin','<label title="Tiñe solo el borde con un color oscuro cercano del sprite. 0% desactiva el tinte.">Oscurecer halo <input data-tint type="number" min="0" max="100" step="10" value="70" aria-label="Intensidad de tinte del borde" style="width:60px"> %</label>');
  q('refine-alpha').insertAdjacentHTML('beforebegin','<label title="Conserva RGB y alpha en cortes rectos con color de relleno detectados en los extremos del original. Detección aproximada."><input data-seams type="checkbox" checked> Proteger empalmes rectos</label>');
  const edgeSettings=document.createElement('section');edgeSettings.className='ar-edge-settings';
  const edgeSummary=document.createElement('strong');edgeSummary.textContent='Limpiar borde';edgeSettings.append(edgeSummary);
  const edgeBody=document.createElement('div');edgeBody.className='ar-edge-controls';
  for(const label of panel.querySelectorAll('.ar-bottom > label'))edgeBody.append(label);
  const magentaButton=document.createElement('button');magentaButton.textContent='Quitar magenta y limpiar borde';magentaButton.title='Quita fondo magenta exterior y descontamina el borde. Crea otra versión local.';magentaButton.onclick=()=>refineAlpha(true);edgeBody.append(q('refine-alpha'),magentaButton);const outlineButtons=['white-2','red-4'].map(preset=>{const b=document.createElement('button');b.textContent=preset==='white-2'?'Contorno blanco · 2 px':'Contorno rojo · 4 px';b.title='Añade contorno exterior en píxeles del PNG. No agranda el lienzo; el borde se recorta si toca sus límites.';b.onclick=()=>refineAlpha(false,preset);edgeBody.append(b);return b;});edgeSettings.append(edgeBody);panel.querySelector('.ar-bottom').append(edgeSettings);
  let jobs=[],versions=[],selected=null,info=null,timer=null,signature='',busy=false,zoom=1,px=0,py=0,drag=null,closed=false,refreshSerial=0,actionMessage='';
  const review={panel,close(){closed=true;clearTimeout(timer);panel.remove();if(assetReview===review)assetReview=null;try{sessionStorage.removeItem('monkey-review-route');}catch{};assetGrid.open().catch(error=>message(error.message,true));}};assetReview=review;
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
  function jobStatus(job){return job?.status==='running'?({wonder:'1/2 · Escalando con Wonder',matting:'2/2 · Topaz extrayendo transparencia', 'bria-alpha':'2/2 · Bria extrayendo transparencia'}[job.stage]||'Procesando'):imageLabStates[job?.status]||'Sin imagen';}
  function selectedVersion(){return versions.find(v=>v.key===selected);}
  function isCurrent(v){return v.kind==='current'||!!(v.job?.candidate_sha256&&v.job.candidate_sha256===info.current_sha256&&(!info.selected_variant||info.selected_variant.job_id===v.job.id));}
  function showVersion(key,chooseBase=false){
    selected=key;const v=selectedVersion();if(!v)return;
    if(chooseBase&&v.url&&[...q('base').options].some(o=>o.value===key)){q('base').value=key;updateBasePreview();}
    if(!closed){try{sessionStorage.setItem('monkey-review-route',JSON.stringify({asset:frame.id,version:key}));}catch{}}
    q('version-title').textContent=v.label;q('result').hidden=!v.url;q('empty').hidden=!!v.url;
    if(v.url){if(q('result').getAttribute('src')!==v.url)q('result').src=v.url;}else{q('result').removeAttribute('src');q('result-size').textContent='';q('empty').textContent=v.job?.error||jobStatus(v.job)||'Sin imagen';}
    q('status').textContent=actionMessage||v.job?.error||(isCurrent(v)?'✓ Esta versión está en uso.':v.job?.quality?.passed===false?'Aviso automático: '+v.job.quality.issues.join(', ')+'. Podés elegir usarla igualmente.':v.job?jobStatus(v.job)+' · '+v.job.model:'Guardado anterior. Restaurarlo conserva también tu versión actual.');
    q('use').disabled=busy||!v.url||isCurrent(v);
    q('use').textContent=busy?'Aplicando…':isCurrent(v)?'✓ Versión en uso':'Usar esta versión';
    q('manual').disabled=busy||!v.url;
    q('refine-alpha').disabled=busy||!v.url;magentaButton.disabled=busy||!v.url;for(const b of outlineButtons)b.disabled=busy||!v.url;
    q('layer').disabled=busy||!v.url||v.kind==='current';
    for(const button of q('history').children)button.setAttribute('aria-pressed',String(button.dataset.key===key));
  }
  function renderHistory(history){
    versions=[{key:'current',kind:'current',label:'En uso',url:info.image}];
    for(const job of jobs)versions.push({key:job.id,kind:'job',label:job.model,job,url:job.image});
    for(const name of history.items)versions.push({key:name,kind:'save',label:'Guardado · '+new Date(Number(name.split('-')[0])/1e6).toLocaleString(),url:'/api/version?id='+frame.id+'&name='+name});
    q('history').replaceChildren();q('count').textContent=versions.length;
    for(const v of versions){const b=document.createElement('button');b.className='ar-version';b.dataset.key=v.key;b.setAttribute('aria-label','Comparar '+v.label+(v.job?' · '+v.job.id.slice(-6):''));b.setAttribute('aria-pressed','false');
      if(v.url){const img=document.createElement('img');img.src=v.url;img.loading='lazy';img.alt='';b.append(img);}
      const text=document.createElement('span'),title=document.createElement('strong'),meta=document.createElement('small');title.textContent=v.label;
      const current=isCurrent(v);b.dataset.current=String(!!current);
      meta.textContent=v.job?(current?'✓ EN USO':v.job.quality?.passed===false?'Con alertas':v.job.status==='applied'?'Usada anteriormente':jobStatus(v.job))+' · '+new Date(v.job.created_at*1000).toLocaleTimeString():v.kind==='current'?(info.selected_variant?.model||'Último guardado manual'):'Edición conservada';text.append(title,meta);b.append(text);b.onclick=()=>{if(busy)return;actionMessage='';showVersion(v.key,true);};q('history').append(b);}
    const base=q('base').value;q('base').replaceChildren(new Option('Original','original'));
    for(const v of versions.filter(v=>v.url))q('base').add(new Option(v.label+(v.job?' · '+new Date(v.job.created_at*1000).toLocaleTimeString()+' · '+v.key.slice(-6):''),v.key));
    if([...q('base').options].some(o=>o.value===base))q('base').value=base;
    if(!versions.some(v=>v.key===selected))selected=initialJob&&versions.some(v=>v.key===initialJob)?initialJob:info.revision?'current':jobs.find(j=>j.image)?.id||'current';
    showVersion(selected,!baseInitialized);baseInitialized=true;updateBasePreview();
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
  function modelChanged(){const ai=q('model').value.startsWith('ai:');q('ai-options').hidden=!ai;q('recipe').textContent=q('model').value.includes('Wonder 3.5')?'Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.':ai?'La base marcada se envía para editar. El original acompaña como referencia de pose y color. Consume ImageLab.':'Original → escalado ×4. Cada envío crea una variante y consume Replicate.';}
  q('model').onchange=()=>{modelChanged();updateBasePreview();};
  q('refine-alpha').onclick=()=>refineAlpha(false);
  async function refineAlpha(removeMagenta,outline=null){
    const v=selectedVersion();if(busy||!v?.url)return;
    busy=true;showVersion(selected);
    try{
      const job=await api('/api/variants/refine-alpha',{id:frame.id,revision:info.revision,outline,remove_magenta:removeMagenta,trim_pixels:Number(q('trim').value),protect_dark:q('dark').checked,tint_strength:Number(q('tint').value)/100,protect_seams:q('seams').checked,...(v.kind==='job'?{job_id:v.job.id}:v.kind==='save'?{history:v.key}:{})});
      selected=job.id;actionMessage='';q('message').textContent='Limpieza local enviada. Sin IA ni créditos; queda como otra versión.';await refresh(true);
    }catch(error){actionMessage=error.message;}finally{busy=false;showVersion(selected);}
  };
  q('generate').onclick=async()=>{
    q('generate').disabled=true;q('message').textContent='Agregando a la cola…';
    try{const value=q('model').value,base=q('base').value,v=versions.find(v=>v.key===base);const source=base==='original'?{}:v?.kind==='current'?{base_kind:'current',base_revision:info.revision}:v?.kind==='save'?{base_kind:'history',base_history:v.key}:{upscale_job_id:base};const job=!value.startsWith('ai:')?await api('/api/upscale/jobs',{id:frame.id,enhance_model:value.slice(value.indexOf(':')+1)}):await api('/api/imagelab/jobs',{id:frame.id,model:value.slice(3),prompt:q('prompt').value,preserve_alpha:true,alpha_mode:'ai',style_id:'',...source});
      selected=job.id;await refresh(true);q('message').textContent='En cola. Podés probar otro modelo o volver a la grilla.';
    }catch(error){q('message').textContent=error.message;}finally{q('generate').disabled=false;}
  };
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
  api('/api/imagelab/status').then(connection=>{if(closed||!connection.ready)return;const group=document.createElement('optgroup');group.label='Redibujo · ImageLab';for(const model of connection.models||[])group.append(new Option(model,'ai:'+model));q('model').append(group);}).catch(()=>{});
}







