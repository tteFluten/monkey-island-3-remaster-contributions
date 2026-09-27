'use strict';
// One review surface per asset. Selecting a version only changes the preview.
let assetReview=null;
async function openAssetReview(frame, initialJob=null){
  if(assetReview){assetReview.close();}
  const panel=document.createElement('section');panel.className='ar-workspace';panel.setAttribute('aria-label','Comparación de asset');
  panel.innerHTML=`<header class="ar-header"><button data-back>← Assets</button><div><small>COMPARAR Y REFINAR</small><h1 data-name></h1></div><span data-summary></span></header>
  <div class="ar-layout"><main class="ar-main"><div class="ar-toolbar"><span>Vista sincronizada</span><button data-fit>Ajustar</button><button data-minus aria-label="Alejar comparación">−</button><output data-zoom>100%</output><button data-plus aria-label="Acercar comparación">+</button><select data-background aria-label="Fondo de comparación"><option value="checker">Transparencia</option><option value="#999da3">Gris</option><option value="#fafafa">Blanco</option><option value="#17191d">Oscuro</option><option value="#ff00ff">Magenta</option></select></div>
  <div class="ar-canvases"><figure><figcaption><strong>Original</strong><span data-original-size></span></figcaption><div class="ar-image-area"><img data-original alt="Original del juego" draggable="false"></div></figure><figure><figcaption><strong data-version-title>Resultado</strong><span data-result-size></span></figcaption><div class="ar-image-area"><img data-result alt="Versión seleccionada" draggable="false"><p data-empty hidden></p></div></figure></div>
  <div class="ar-bottom"><p data-status role="status"></p><button data-use>Usar esta versión</button><button data-manual class="accent">Retocar esta versión en Confite</button></div></main>
  <aside class="ar-sidebar"><section class="ar-generate"><h2>Crear otra versión</h2><label>Modelo<select data-model aria-label="Modelo para nueva versión"><optgroup label="Topaz · API directa"><option value="upscale:Wonder 3.5 High + Bria">Wonder 3.5 High ×4 + Bria</option></optgroup><optgroup label="Escalado · Replicate"><option value="upscale:Real-ESRGAN Anime 6B">Real-ESRGAN · Anime 6B ×4</option><option value="topaz:CGI">Topaz · CGI</option><option value="topaz:High Fidelity V2">Topaz · Alta fidelidad</option><option value="topaz:Standard V2">Topaz · Estándar</option><option value="topaz:Low Resolution V2">Topaz · Baja resolución</option></optgroup></select></label><div data-ai-options hidden><label>Base<select data-base aria-label="Base para ImageLab"><option value="original">Original</option></select></label><label>Instrucciones<textarea data-prompt rows="3"></textarea></label></div><p data-recipe>Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.</p><button data-generate class="accent">Generar versión</button><p data-message role="status"></p></section>
  <section class="ar-versions"><div class="ar-section-title"><h2>Versiones</h2><span data-count></span></div><p class="ar-hint">Seleccioná para comparar. El trabajo actual solo cambia al usar o retocar una versión.</p><div data-history></div></section></aside></div>`;
  document.body.append(panel);
  const q=k=>panel.querySelector('[data-'+k+']');q('name').textContent=frame.name;q('prompt').value=imageLabDefaultPrompt;
  let jobs=[],versions=[],selected=null,info=null,timer=null,signature='',busy=false,zoom=1,px=0,py=0,drag=null,closed=false,refreshSerial=0,actionMessage='';
  const review={panel,close(){closed=true;clearTimeout(timer);panel.remove();if(assetReview===review)assetReview=null;assetGrid.open().catch(error=>message(error.message,true));}};assetReview=review;
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
    area.onpointerdown=e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY};area.setPointerCapture(e.pointerId);};
    area.onpointermove=e=>{if(!drag)return;px+=e.clientX-drag.x;py+=e.clientY-drag.y;drag={x:e.clientX,y:e.clientY};transform();};
    area.onpointerup=area.onpointercancel=()=>{drag=null;};
  }
  q('background').onchange=()=>{for(const area of panel.querySelectorAll('.ar-image-area')){area.style.background=q('background').value==='checker'?'':q('background').value;}};
  function jobStatus(job){return job?.status==='running'?({wonder:'1/2 · Escalando con Wonder',matting:'2/2 · Topaz extrayendo transparencia', 'bria-alpha':'2/2 · Bria extrayendo transparencia'}[job.stage]||'Procesando'):imageLabStates[job?.status]||'Sin imagen';}
  function selectedVersion(){return versions.find(v=>v.key===selected);}
  function isCurrent(v){return v.kind==='current'||!!(v.job?.candidate_sha256&&v.job.candidate_sha256===info.current_sha256&&(!info.selected_variant||info.selected_variant.job_id===v.job.id));}
  function showVersion(key){
    selected=key;const v=selectedVersion();if(!v)return;
    q('version-title').textContent=v.label;q('result').hidden=!v.url;q('empty').hidden=!!v.url;
    if(v.url){if(q('result').getAttribute('src')!==v.url)q('result').src=v.url;}else{q('result').removeAttribute('src');q('result-size').textContent='';q('empty').textContent=v.job?.error||jobStatus(v.job)||'Sin imagen';}
    q('status').textContent=actionMessage||v.job?.error||(isCurrent(v)?'✓ Esta versión está en uso.':v.job?.quality?.passed===false?'Aviso automático: '+v.job.quality.issues.join(', ')+'. Podés elegir usarla igualmente.':v.job?jobStatus(v.job)+' · '+v.job.model:'Guardado anterior. Restaurarlo conserva también tu versión actual.');
    q('use').disabled=busy||!v.url||isCurrent(v);
    q('use').textContent=busy?'Aplicando…':isCurrent(v)?'✓ Versión en uso':'Usar esta versión';
    q('manual').disabled=busy||!v.url;
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
      meta.textContent=v.job?(current?'✓ EN USO':v.job.quality?.passed===false?'Con alertas':v.job.status==='applied'?'Usada anteriormente':jobStatus(v.job))+' · '+new Date(v.job.created_at*1000).toLocaleTimeString():v.kind==='current'?(info.selected_variant?.model||'Último guardado manual'):'Edición conservada';text.append(title,meta);b.append(text);b.onclick=()=>{if(busy)return;actionMessage='';showVersion(v.key);};q('history').append(b);}
    const base=q('base').value;q('base').replaceChildren(new Option('Original','original'));
    for(const j of jobs.filter(j=>j.operation==='upscale'&&j.image&&j.quality?.passed!==false))q('base').add(new Option(j.model+' · '+new Date(j.created_at*1000).toLocaleTimeString(),j.id));
    if([...q('base').options].some(o=>o.value===base))q('base').value=base;
    if(!versions.some(v=>v.key===selected))selected=initialJob&&versions.some(v=>v.key===initialJob)?initialJob:info.revision?'current':jobs.find(j=>j.image)?.id||'current';
    showVersion(selected);
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
  function modelChanged(){const ai=q('model').value.startsWith('ai:');q('ai-options').hidden=!ai;q('recipe').textContent=q('model').value.includes('Wonder 3.5')?'Original → Wonder ×4 → Bria (Replicate). Reutiliza Wonder si ya existe; Bria se cobra por separado.':ai?'Original como referencia de pose y color. Podés limpiar un escalado anterior. Consume ImageLab.':'Original → escalado ×4. Cada envío crea una variante y consume Replicate.';}
  q('model').onchange=modelChanged;
  q('generate').onclick=async()=>{
    q('generate').disabled=true;q('message').textContent='Agregando a la cola…';
    try{const value=q('model').value;const job=!value.startsWith('ai:')?await api('/api/upscale/jobs',{id:frame.id,enhance_model:value.slice(value.indexOf(':')+1)}):await api('/api/imagelab/jobs',{id:frame.id,model:value.slice(3),prompt:q('prompt').value,preserve_alpha:true,alpha_mode:'ai',style_id:'',...(q('base').value!=='original'?{upscale_job_id:q('base').value}:{})});
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
  q('manual').onclick=async()=>{
    if(busy)return;busy=true;actionMessage='Abriendo la versión seleccionada…';showVersion(selected);
    try{
      await save();await useSelected(true);
      const sequence=state.groups.find(g=>g[0].group===frame.group);if(!sequence)throw new Error('No se encontró la secuencia.');
      state.busy=false;await navigate(sequence.findIndex(f=>f.id===frame.id),sequence);
      if(state.info?.frame.id!==frame.id)throw new Error('No se pudo cargar el asset.');
      await confiteButton.onclick();if(!confiteSession)throw new Error('No se pudo abrir Confite.');
      panel.hidden=true;const grid=document.querySelector('.asset-browser');if(grid)grid.hidden=true;
      confiteSession.overlay.querySelector('[data-close]').textContent='Guardar y volver a comparación';
      confiteSession.onReviewReturn=()=>{if(closed)return;panel.hidden=false;selected='current';refresh(true);};
    }catch(error){actionMessage=error.message;await refresh(true);}finally{busy=false;if(panel.hidden)actionMessage='';showVersion(selected);}
  };
  await refresh(true);
  // Availability of the generator never blocks viewing local results.
  api('/api/imagelab/status').then(connection=>{if(closed||!connection.ready)return;const group=document.createElement('optgroup');group.label='Redibujo · ImageLab';for(const model of connection.models||[])group.append(new Option(model,'ai:'+model));q('model').append(group);}).catch(()=>{});
}
