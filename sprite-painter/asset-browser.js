'use strict';
// A virtual canvas: only visible cards are painted and at most six thumbnails load together.
const assetGrid = (() => {
  let panel, canvas, ctx, collection, search, filter, order, statusLine, zoomLabel, actionLayer;
  let items=[], cols=4, scale=1, panX=18, panY=18, width=0, height=0, active=false, opening=false, selected=-1;
  let CW=210, CH=258;
  const cache=new Map(), loading=new Set(), queue=[], actions=new Map();
  const picked=new Set(), selectionButtons=new Map();
  let selectionMode=false, selectionAnchor=null, visibleIds=[];
  let viewMode='sequences',sequences=[],sequenceScope=null,sequenceReturn=null;
  let viewReady=false,lastStoredView='';
  let batchId=null,batchFilter=null,batchReturn=null,batchBar=null,batchSignature='';
  const batchLabels={all:'Todos',pending:'Sin enviar',queued:'En cola',running:'Generando',ready:'Para revisar',applied:'Aplicados',approved:'Aprobados',error:'Errores'};
  const batchColors={pending:'#eac264',queued:'#73adff',running:'#73adff',ready:'#eac264',applied:'#77ce98',approved:'#77ce98',error:'#ff6969'};
  function snapshotView(){
    return {filters:sequenceFilters().map(el=>el.value),density:panel.querySelector('[data-density]').value,
      panX,panY,scale,cols,viewMode,sequenceScope,sequenceReturn,selectionMode,selectionAnchor,
      picked:[...picked],focused:entries()[selected]?.id,batchId,batchFilter,batchReturn};
  }
  function rememberView(){
    if(!viewReady||!panel)return;
    try{const value=JSON.stringify(snapshotView());if(value!==lastStoredView){sessionStorage.setItem('monkey-assets-view',value);lastStoredView=value;}}catch{}
  }
  function savedView(){
    try{
      const key=new URLSearchParams(location.search).get('browser');
      // A tab inherits the exact grid snapshot from which its detail was opened.
      const value=sessionStorage.getItem('monkey-assets-view')||(key&&localStorage.getItem('monkey-assets-return:'+key));
      const saved=JSON.parse(value||'null');return Array.isArray(saved?.filters)&&saved.filters.length===8?saved:null;
    }catch{return null;}
  }
  function restoreView(saved){
    sequenceFilters().forEach((el,i)=>{el.value=saved.filters[i];});
    // If saved view had "all collections", pick a default scene instead
    if(!collection.value&&[...collection.options].some(o=>o.value)){const preferred=['Barco · personajes','Agua · personajes'];collection.value=preferred.find(c=>[...collection.options].some(o=>o.value===c))||collection.options[1]?.value||'';}
    panel.querySelector('[data-density]').value=saved.density||'210';
    viewMode=saved.viewMode==='assets'?'assets':'sequences';sequenceScope=saved.sequenceScope||null;sequenceReturn=saved.sequenceReturn||null;
    selectionMode=!!saved.selectionMode;selectionAnchor=saved.selectionAnchor||null;
    picked.clear();for(const id of saved.picked||[])if(state.frames.some(f=>f.id===id))picked.add(id);
    batchId=saved.batchId||null;batchFilter=saved.batchFilter||null;batchReturn=saved.batchReturn||null;
    rebuild(true);
    if([saved.panX,saved.panY,saved.scale,saved.cols].every(Number.isFinite)&&saved.scale>=.25&&saved.scale<=3&&saved.cols>=1&&saved.cols<=12){({panX,panY,scale,cols}=saved);}
    selected=entries().findIndex(f=>f.id===saved.focused);
  }
  window.addEventListener('pagehide',rememberView);
  function entries(){return viewMode==='sequences'?sequences:items;}
  function entryIds(entry){return entry.frames?entry.frames.map(f=>f.id):[entry.id];}
  function listedIds(){return entries().flatMap(entryIds);}
  let auditResults={},auditProgress={},auditTimer=null;
  let batchSending=false,batchStop=false;
  function edgeState(f){const j=imageLabAssetJobs.get(f.id);return f.edge_cleaned?'applied':j?.operation==='local-alpha'&&j.base_revision===f.revision&&['ready','queued','running'].includes(j.status)?'prepared':'none';}
  function actionCandidates(){return selectionMode?state.frames.filter(f=>picked.has(f.id)):viewMode==='sequences'?sequences.flatMap(g=>g.frames):items;}
  function batchTargets(approval=false){
    const scope=panel.querySelector('[data-batch-scope]')?.value||'filtered';
    const candidates=selectionMode?actionCandidates():scope==='all'?state.frames:scope==='collection'?state.frames.filter(f=>!collection.value||f.category===collection.value):items;
    return candidates.filter(f=>approval?imageLabNeedsApproval(f):(!imageLabApprovals[f.id]||!panel.querySelector('[data-skip-approved]').checked)&&(!panel.querySelector('[data-batch-seams]')?.checked||f.has_reference)&&edgeState(f)==='none');
  }
  function updateSelectionBar(){
    if(!panel)return;
    const inList=new Set(items.map(f=>f.id)),hidden=[...picked].filter(id=>!inList.has(id)).length;
    const count=panel.querySelector('[data-selection-count]'),approved=[...picked].filter(id=>imageLabApprovals[id]).length;
    count.textContent=selectionMode?`${picked.size} seleccionados${approved?` · ${approved} ya aprobados`:''}${hidden?` · ${hidden} fuera del filtro`:''}`:'Clic para abrir · marcá las casillas para elegir varios';
    const toggle=panel.querySelector('[data-selection-mode]');
    toggle.setAttribute('aria-pressed',String(selectionMode));
    toggle.querySelector('span:last-child').textContent=selectionMode?'Terminar selección':'Seleccionar';
    panel.classList.toggle('is-selecting',selectionMode);
    panel.querySelector('[data-selection-clear]').disabled=picked.size===0;
    panel.querySelector('[data-select-visible]').disabled=visibleIds.length===0;
    panel.querySelector('[data-select-all]').disabled=items.length===0;
    for(const button of panel.querySelectorAll?.('[data-selection-action]')||[]){button.hidden=!selectionMode;button.disabled=batchSending||picked.size===0;}
  }
  function updateBatchControls(){
    if(!panel)return;
    const scope=panel.querySelector('[data-batch-scope]');
    if(selectionMode)scope.value='selected';else if(scope.value==='selected')scope.value='filtered';
    scope.disabled=selectionMode;scope.querySelector('[value=selected]').hidden=!selectionMode;
    const candidates=actionCandidates(),approve=candidates.filter(imageLabNeedsApproval).length;
    const clean=candidates.filter(f=>f.has_reference&&!imageLabApprovals[f.id]&&edgeState(f)==='none').length;
    const redo=candidates.filter(f=>f.has_reference&&!imageLabApprovals[f.id]&&auditInfo(f)?.score>=2).length;
    for(const [selector,label,count] of [
      ['[data-batch]','Crear versiones',batchTargets().length],
      ['[data-batch-approve]','Aprobar',batchTargets(true).length],
      ['[data-approve-visible]',selectionMode?'Aprobar selección':'Aprobar listado',approve],
      ['[data-clean-auto]','Limpiar bordes',clean],['[data-redo]','Rehacer desviados',redo]
    ]){const button=panel.querySelector(selector);button.textContent=`${label} (${count})`;button.disabled=batchSending||count===0;}
    const analyzeButton=panel.querySelector('[data-audit-filtered]');
    analyzeButton.textContent=selectionMode?`Analizar selección (${candidates.length})`:'Analizar listado';
    analyzeButton.disabled=!!auditProgress.running||candidates.length===0;
    panel.querySelector('.ab-action-hint').textContent=selectionMode?'Sólo selección · Rehacer consume créditos':'Listado actual · Rehacer consume créditos';
    panel.querySelector('[data-clean-auto]').title=(selectionMode?'Selección':'Listado actual')+' · recorte 0,5 px y tinte 70% · protege empalmes · omite aprobados y limpiezas existentes';
    const globalPR=panel.querySelector('.ab-global-pr');
    if(globalPR){const count=state.frames.filter(f=>imageLabApprovals[f.id]).length;globalPR.textContent=count?`Enviar PR (${count} aprobados)`:'Enviar PR con aprobados';globalPR.disabled=!count;}
    updateSelectionBar();
    rememberView();
  }
  function selectionChanged(){updateBatchControls();invalidate();}
  function pick(index,range=false){
    const list=entries(),frame=list[index];if(!frame)return;
    selectionMode=true;selected=index;
    const anchor=list.findIndex(f=>f.id===selectionAnchor);
    if(range&&anchor>=0){for(let i=Math.min(anchor,index);i<=Math.max(anchor,index);i++)for(const id of entryIds(list[i]))picked.add(id);}
    else{const ids=entryIds(frame),all=ids.every(id=>picked.has(id));for(const id of ids){if(all)picked.delete(id);else picked.add(id);}selectionAnchor=frame.id;}
    selectionChanged();
  }
  function pickMany(ids){selectionMode=true;for(const id of ids)picked.add(id);selectionChanged();}
  function clearSelection(exit=false){picked.clear();selectionAnchor=null;if(exit)selectionMode=false;selectionChanged();}
  function trackedEntry(frame){return batchFilter&&SpriteBatches.entry(batchId,frame.id);}
  function focusBatch(value){
    if(value&&!batchFilter)batchReturn={panX,panY,scale,cols,viewMode,selected};
    batchFilter=value;if(value)viewMode='assets';
    rebuild(true);if(!value&&batchReturn){({panX,panY,scale,cols,viewMode,selected}=batchReturn);batchReturn=null;rebuild(true);}else{panX=18;panY=18;}
    rememberView();invalidate();
  }
  function renderBatchBar(){
    if(!batchBar)return;
    const batches=SpriteBatches.all();batchBar.hidden=false;
    batchBar.querySelector('[data-batch-follow]').disabled=!state.frames.length;
    batchBar.classList.toggle('is-empty',!batches.length);
    if(!SpriteBatches.get(batchId))batchId=batches[0]?.id||null;
    const batch=SpriteBatches.get(batchId);if(!batch)return;
    const counts=SpriteBatches.counts(batch),signature=JSON.stringify([batches.map(b=>[b.id,b.label]),batch.id,counts,batchFilter,batch.entries.map(e=>e.error)]);
    if(signature===batchSignature)return;batchSignature=signature;
    const select=batchBar.querySelector('select'),chosen=select.value;
    if([...select.options].map(o=>o.value).join()!==batches.map(b=>b.id).join())select.replaceChildren(...batches.map(b=>new Option(b.label+' · '+new Date(b.created).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}),b.id)));
    select.value=batch.id;
    const finished=counts.ready+counts.applied+counts.approved;
    batchBar.querySelector('output').textContent=`${finished}/${counts.all} completados`+(batchFilter?' · filtros guardados':'');
    batchBar.querySelector('progress').max=counts.all;batchBar.querySelector('progress').value=finished;
    for(const button of batchBar.querySelectorAll('[data-batch-state]')){const key=button.dataset.batchState;button.textContent=batchLabels[key]+' '+counts[key];button.setAttribute('aria-pressed',String(batchFilter===key));button.disabled=key!=='all'&&!counts[key];}
    batchBar.querySelector('[data-batch-return]').hidden=!batchFilter;
    batchBar.querySelector('[data-batch-review]').disabled=!counts.ready;
    batchBar.querySelector('[data-batch-apply]').disabled=!counts.ready;
    batchBar.querySelector('[data-batch-pr]').disabled=!counts.approved;batchBar.querySelector('[data-batch-pr]').textContent='PR de aprobados ('+counts.approved+')';
  }
  function createBatchBar(stage){
    batchBar=document.createElement('section');batchBar.className='ab-batch-tracker';batchBar.setAttribute('aria-label','Seguimiento de tandas');
    batchBar.innerHTML='<div class="ab-batch-heading"><strong>Tanda</strong><select aria-label="Tanda a seguir"></select><progress aria-label="Resultados completados"></progress><output role="status"></output><button data-batch-follow>Seguir selección / listado</button><button data-batch-review>Revisar resultados</button><button data-batch-apply>Aplicar resultados</button><button data-batch-pr>PR de aprobados</button><button data-batch-return hidden>Volver al listado</button></div><div class="ab-batch-states" aria-label="Estado de la tanda"></div>';
    batchBar.querySelector('[data-batch-follow]').onclick=async()=>{const button=batchBar.querySelector('[data-batch-follow]'),frames=[...actionCandidates()];if(!frames.length)return;button.disabled=true;try{await SequenceTools.refreshAssets(frames.map(f=>f.id));const batch=SpriteBatches.begin(frames.map(f=>({name:f.name,body:{id:f.id}})),'Últimos trabajos del listado');batchId=batch.id;for(const frame of frames){const job=[imageLabAssetJobs.get(frame.id),imageLabResultJobs.get(frame.id)].filter(Boolean).sort((a,b)=>b.created_at-a.created_at)[0];SpriteBatches.update(batch.id,frame.id,job?{status:'sent',job}:{status:'unsent',error:'Sin generación registrada para este asset.'});}SpriteBatches.ingest([],imageLabApprovals);focusBatch('all');}catch(e){imageLabNotice(e.message);}finally{button.disabled=false;}};
    for(const key of Object.keys(batchLabels)){const button=document.createElement('button');button.dataset.batchState=key;button.style.setProperty('--batch-color',batchColors[key]||'#ddd');button.onclick=()=>focusBatch(key);batchBar.querySelector('.ab-batch-states').append(button);}
    batchBar.querySelector('select').onchange=e=>{batchId=e.target.value;focusBatch('all');};
    batchBar.querySelector('[data-batch-return]').onclick=()=>focusBatch(null);
    batchBar.querySelector('[data-batch-pr]').onclick=()=>{const ids=SpriteBatches.get(batchId)?.entries.filter(e=>SpriteBatches.state(e)==='approved').map(e=>e.asset_id)||[];if(ids.length)showSelectionPR(ids);};
    const readyEntries=()=>SpriteBatches.get(batchId)?.entries.filter(e=>SpriteBatches.state(e)==='ready')||[];
    batchBar.querySelector('[data-batch-review]').onclick=()=>{const ready=readyEntries();if(ready.length){focusBatch('ready');openGridReview(ready[0].asset_id,ready.map(e=>e.asset_id));}};
    batchBar.querySelector('[data-batch-apply]').onclick=()=>{const ready=readyEntries(),ids=new Set(ready.map(e=>e.asset_id));SequenceTools.reviewResults(state.frames.filter(f=>ids.has(f.id)),new Map(ready.map(e=>[e.asset_id,e.job.id]))).catch(e=>imageLabNotice(e.message));};
    stage.before(batchBar);SpriteBatches.subscribe(()=>{renderBatchBar();if(panel&&viewReady)rebuild(true);});renderBatchBar();
  }
  async function runSelectionBatch(requests,label,progress=()=>{},contextFrames=[]){
    if(batchSending)throw new Error('Ya se está enviando un lote. Podés detener su envío antes de iniciar otro.');
    batchSending=true;batchStop=false;let sent=0;const errors=[];
    const membership=contextFrames.length?contextFrames.map(f=>({body:{id:f.id},name:f.name})):requests;
    const batch=SpriteBatches.begin(membership,label);batchId=batch.id;
    const sending=new Set(requests.map(r=>r.body.id));
    for(const f of contextFrames)if(!sending.has(f.id)){const job=imageLabAssetJobs.get(f.id);SpriteBatches.update(batch.id,f.id,job&&['queued','running'].includes(job.status)?{status:'sent',job}:{status:'error',error:'Sin original asociado · no enviado.'});}
    focusBatch('all');
    const output=panel.querySelector('[data-batch-status]'),stop=panel.querySelector('[data-batch-stop]');
    const report=text=>{output.textContent=text;progress(text);};
    stop.hidden=false;updateBatchControls();
    try{for(const request of requests){
      if(batchStop)break;
      report(`${label} · enviando ${sent+errors.length+1}/${requests.length}`);
        SpriteBatches.update(batch.id,request.body.id,{status:'sending'});
        try{const job=await api(request.url,request.body);sent++;SpriteBatches.update(batch.id,request.body.id,{status:'sent',job});if(job.asset_id){imageLabAssetJobs.set(job.asset_id,job);window.dispatchEvent(new Event('imagelab-assets'));LiveAssets.request([job.asset_id]);}}catch(error){errors.push(request.name+': '+error.message);SpriteBatches.update(batch.id,request.body.id,{status:'error',error:error.message});}
    }}finally{
      batchSending=false;stop.hidden=true;
      SpriteBatches.finish(batch.id);
        report(`${sent} encolados · ${errors.length} errores${batchStop?' · envío detenido':''}. Al terminar, usá Aplicar resultados con esta selección.`);
        output.title=errors.join('\n');updateBatchControls();
        LiveAssets.request(requests.map(r=>r.body.id));
    }
    return {sent,errors};
  }
    function processSelection(technique){
      if(batchSending||!picked.size)return;
      const frames=state.frames.filter(f=>picked.has(f.id));
      if(technique==='source'){SourcePreparation.open(frames);return;}
      if(technique==='pr'){showSelectionPR(frames.map(f=>f.id));return;}
      if(technique==='apply'){SequenceTools.reviewResults(frames).catch(error=>imageLabNotice(error.message));return;}
    if(technique==='wonder'){
      const {requests,skipped}=SequenceTools.plan(frames,{technique:'upscale',model:'Wonder 3.5 High + Bria'},imageLabApprovals,imageLabAssetJobs);
      if(!requests.length){panel.querySelector('[data-batch-status]').textContent=`No hay cuadros para enviar: ${skipped.busy} en proceso · ${skipped.original} sin original.`;return;}
      runSelectionBatch(requests,'Wonder ×4 → Bria',()=>{},frames).then(result=>{
        if(skipped.busy||skipped.original)panel.querySelector('[data-batch-status]').textContent+=` Omitidos: ${skipped.busy} en proceso · ${skipped.original} sin original.`;
        if(result.errors.length)imageLabNotice(`${result.errors.length} errores de envío. ${result.errors[0]}`);
      }).catch(error=>imageLabNotice(error.message));
    }else SequenceTools.open(frames,technique,runSelectionBatch);
  }
  function sequenceFilters(){return [search,collection,filter,order,...['problem','similarity','edge-filter','preset'].map(key=>panel.querySelector('[data-'+key+']'))];}
  function openSequence(group){
    sequenceReturn={values:sequenceFilters().map(el=>el.value),panX,panY,scale,cols};
    sequenceScope=group.key;viewMode='assets';selected=-1;
    search.value='';collection.value=group.category;filter.value='all';order.value='name';
    panel.querySelector('[data-problem]').value='';panel.querySelector('[data-similarity]').value='100';panel.querySelector('[data-edge-filter]').value='all';panel.querySelector('[data-preset]').value='all';
    rebuild();fit();
  }
  function setView(mode){
    if(sequenceScope&&sequenceReturn){sequenceFilters().forEach((el,i)=>el.value=sequenceReturn.values[i]);}
    sequenceScope=null;viewMode=mode;selected=-1;rebuild();
    if(mode==='sequences'&&sequenceReturn){({panX,panY,scale,cols}=sequenceReturn);sequenceReturn=null;invalidate();}else{sequenceReturn=null;fit();}
  }
  function updateViewControls(){
    for(const b of panel.querySelectorAll('[data-view]'))b.setAttribute('aria-pressed',String(b.dataset.view===viewMode));
    const breadcrumb=panel.querySelector('.ab-sequence-path');breadcrumb.hidden=!sequenceScope||!!batchFilter;
    if(sequenceScope){const group=sequences.find(g=>g.key===sequenceScope);breadcrumb.querySelector('[data-sequence-title]').textContent=(group?.name||'Secuencia')+' · '+items.length+' cuadros';}
    panel.querySelector('[data-sequence-note]').hidden=viewMode!=='sequences';
  }
  // Agreement at native resolution, not a probability of artistic quality.
  function similarity(report){
    const m=report?.metrics;if(!m)return null;
    const clamp=v=>Math.max(0,Math.min(1,v));
    return Math.round(100*(1-(.3*clamp(m.shape)+.25*clamp(m.color/255)+.15*clamp(m.edge)+.2*clamp(m.ink)+.1*clamp(m.halo/255))));
  }
  function auditInfo(frame){const a=auditResults[frame.id];return a?.current?a:null;}
  function cardReview(frame){const a=auditInfo(frame);return a?{priority:a.passed?0:2,text:a.passed?'Sin desvíos detectados':a.issues.join(' · ')}:reviewInfo(frame);}
  async function refreshAudit(){
    clearTimeout(auditTimer);
    try{const wasRunning=auditProgress.running;const data=await api('/api/asset-audit');auditResults=data.results;auditProgress=data.progress;
      const label=panel?.querySelector('[data-audit-status]');if(label)label.textContent=auditProgress.running?`Analizando ${auditProgress.done}/${auditProgress.total}`:`${Object.values(auditResults).filter(a=>a.current&&!a.passed).length} con desvíos · ${auditProgress.errors||0} sin evaluar`;
      panel?.querySelectorAll('[data-audit-run]').forEach(b=>b.disabled=auditProgress.running);if(wasRunning&&!auditProgress.running)rebuild();updateBatchControls();invalidate();
    }catch(error){if(statusLine)statusLine.textContent=error.message;}
    if(active&&auditProgress.running)auditTimer=setTimeout(refreshAudit,2500);
  }
  async function analyze(ids){try{await api('/api/asset-audit',{ids,strict:panel.querySelector('[data-audit-strict]').checked});await refreshAudit();}catch(error){imageLabNotice(error.message);}}
  let running=0, scheduled=false, drag=null;
  function invalidate(){if(!active||scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;if(active)draw();});}
  window.addEventListener('imagelab-assets',()=>{updateBatchControls();invalidate();});
  window.addEventListener('assets-live',event=>{
    for(const id of event.detail.changed){
      if(auditResults[id])auditResults[id].current=false;
      // Evict cached thumbnails so the grid shows updated artwork
      for(const suffix of ['/edit/','/original','/result/']){
        for(const key of cache.keys())if(key.startsWith(id)){cache.get(key)?.close?.();cache.delete(key);}
      }
      // Also clear browser disk cache for this asset's thumbnails
      diskCache.then(s=>s&&s.keys().then(keys=>keys.filter(k=>k.url.includes(id)).forEach(k=>s.delete(k)))).catch(()=>{});
    }
    if(panel)rebuild(true);
  });
  const diskCache=caches.open('monkey-thumbnails').catch(()=>null);
  function trim(){while(cache.size>1024){const key=cache.keys().next().value;cache.get(key)?.close?.();cache.delete(key);}}
  function request(frame,reference,result=null){
    const version=frame.thumbnail_version||frame.revision||'base';
    const key=frame.id+(reference?'/original':result?'/result/'+result.id:'/edit/'+version);
    if(cache.has(key)){const value=cache.get(key);cache.delete(key);cache.set(key,value);return value;}
    if(!loading.has(key)){loading.add(key);queue.push({key,frame,reference,result,version});}
    return undefined;
  }
  function pump(){while(running<30&&queue.length){
    const task=queue.shift();running++;
    const url=task.result?.image||('/api/thumbnail?id='+task.frame.id+'&reference='+(task.reference?1:0)+'&v='+task.version);
    const cacheKey=url;
    (async()=>{try{
      const store=await diskCache;
      const cached=store&&await store.match(cacheKey);
      let blob;
      if(cached){blob=await cached.blob();}
      else{const response=await fetch(url);if(!response.ok)throw new Error('PNG no disponible');blob=await response.blob();if(store)store.put(cacheKey,new Response(blob.slice()));}
      const bitmap=await createImageBitmap(blob);cache.set(task.key,bitmap);trim();
    }catch(_){cache.set(task.key,null);}finally{loading.delete(task.key);running--;invalidate();pump();}})();
  }}
  function text(value,x,y,max,color='#d7dce2',size=11){ctx.fillStyle=color;ctx.font=size+'px Segoe UI';let label=String(value);while(ctx.measureText(label).width>max&&label.length>3)label=label.slice(0,-2);if(label!==String(value))label+='…';ctx.fillText(label,x,y);}
  function picture(bitmap,x,y,w,h,reference){
    ctx.fillStyle='#222222';ctx.fillRect(x,y,w,h);ctx.fillStyle='#292929';
    for(let row=0;row<h/10;row++)for(let col=0;col<w/10;col++)if((row+col)%2===0)ctx.fillRect(x+col*10,y+row*10,Math.min(10,w-col*10),Math.min(10,h-row*10));
    if(bitmap){const ratio=Math.min((w-12)/bitmap.width,(h-12)/bitmap.height);ctx.imageSmoothingEnabled=!reference;ctx.drawImage(bitmap,x+(w-bitmap.width*ratio)/2,y+(h-bitmap.height*ratio)/2,bitmap.width*ratio,bitmap.height*ratio);}
    else text(bitmap===null?'No disponible':'Cargando…',x+10,y+h/2,w-20,'#8491a1',10);
  }
  function drawSequence(group,i,x,y,visibleActions){
    const count=group.frames.filter(f=>picked.has(f.id)).length,all=count===group.frames.length;
    const approved=group.frames.filter(f=>imageLabApprovals[f.id]).length;
    const total=group.frames.length, allApproved=approved===total;
    const pending=group.frames.filter(f=>['queued','running'].includes(imageLabAssetJobs.get(f.id)?.status)).length;
    const ready=group.frames.filter(f=>imageLabAssetJobs.get(f.id)?.status==='ready').length;
    // Card background
    ctx.fillStyle='#1c1f24';ctx.fillRect(x,y,CW-14,CH-14);
    // Border — green if fully approved, white if selected
    const borderColor=count?'#fff':allApproved?'#c4db9e':'#333840';
    ctx.strokeStyle=borderColor;ctx.lineWidth=count||allApproved?2:1;ctx.strokeRect(x+.5,y+.5,CW-15,CH-15);
    // Title
    text(group.name,x+10,y+22,CW-34,'#e4e6ea',12);
    // Thumbnails — show up to 3 preview frames
    const indices=[...new Set([0,Math.floor((total-1)/2),total-1])];
    const tw=(CW-30)/indices.length;
    indices.forEach((index,n)=>{const f=group.frames[index],job=imageLabNeedsApproval(f)?imageLabResultJobs.get(f.id):null;picture(request(f,false,job),x+8+n*tw,y+36,tw-2,130,false);});
    // Status line
    const statusY=y+180;
    text(`${total} cuadros`,x+10,statusY,CW-34,'#aeb7c3',11);
    // Progress bar
    const barY=statusY+8,barW=CW-34,barH=4;
    ctx.fillStyle='#2a2d32';ctx.fillRect(x+10,barY,barW,barH);
    if(approved){ctx.fillStyle='#c4db9e';ctx.fillRect(x+10,barY,barW*approved/total,barH);}
    if(pending){ctx.fillStyle='#73adff';ctx.fillRect(x+10+barW*approved/total,barY,barW*pending/total,barH);}
    // Counts below bar
    const countY=barY+16;
    if(allApproved) text('✓ Todo aprobado',x+10,countY,CW-34,'#c4db9e',10);
    else if(approved) text(`${approved}/${total} aprobados`,x+10,countY,CW-34,'#c4db9e',10);
    else if(pending) text(`${pending} en proceso`,x+10,countY,CW-34,'#73adff',10);
    else if(ready) text(`${ready} para revisar`,x+10,countY,CW-34,'#eac264',10);
    else text('Sin generar',x+10,countY,CW-34,'#666',10);
    // Select checkbox
    let selectButton=selectionButtons.get(group.id);
    if(!selectButton){
      selectButton=ReviewUI.button('Marcar secuencia completa: '+group.name,'check',e=>pick(entries().findIndex(g=>g.id===group.id),e.shiftKey),'ab-select-card');
      selectButton.setAttribute('role','checkbox');selectButton.dataset.sequenceId=group.id;actionLayer.append(selectButton);selectionButtons.set(group.id,selectButton);
    }
    selectButton.setAttribute('aria-checked',all?'true':count?'mixed':'false');
    selectButton.style.transform=`translate(${(x+CW-24)*scale+panX-28}px,${(y+36)*scale+panY}px)`;
    if(scale<.5)return;
    visibleActions.add(group.id);let buttons=actions.get(group.id);
    if(!buttons){
      buttons=document.createElement('div');buttons.className='ab-card-actions ab-seq-actions';
      const open=document.createElement('button');open.className='ab-seq-open';open.textContent='Abrir';open.title='Ver cuadros individuales';
      open.onclick=()=>openSequence(sequences.find(g=>g.id===group.id));
      const approve=document.createElement('button');approve.className='ab-seq-approve';approve.textContent='✓';approve.title='Aprobar toda la secuencia';
      approve.onclick=async()=>{approve.disabled=true;try{for(const f of group.frames){if(!imageLabNeedsApproval(f)&&imageLabApprovals[f.id])continue;try{await acceptLatestImageLabResult(f);}catch{}}invalidate();updateBatchControls();}finally{approve.disabled=false;}};
      const gen=document.createElement('button');gen.className='ab-seq-gen';gen.textContent='⚡';gen.title='Generar con Wonder ×4 → Bria · consume créditos';
      gen.onclick=()=>{picked.clear();group.frames.forEach(f=>picked.add(f.id));selectionMode=true;selectionChanged();processSelection('wonder');};
      buttons.append(open,approve,gen);actions.set(group.id,buttons);actionLayer.append(buttons);
    }
    const approveBtn=buttons.querySelector('.ab-seq-approve');
    approveBtn.textContent=allApproved?'✓':'✓';
    approveBtn.classList.toggle('is-done',allApproved);
    buttons.style.transform=`translate(${x*scale+panX+8*scale}px,${(y+CH-48)*scale+panY}px) scale(${scale})`;
  }
  function draw(){
    const list=entries();
    const dpr=Math.min(devicePixelRatio||1,2);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#101010';ctx.fillRect(0,0,width,height);
    ctx.save();ctx.translate(panX,panY);ctx.scale(scale,scale);
    const first=Math.max(0,Math.floor(-panY/scale/CH)),last=Math.min(Math.ceil(list.length/cols),Math.ceil((height-panY)/scale/CH));
    // Drop requests that have not started when the user pans elsewhere.
    for(const task of queue.splice(0))loading.delete(task.key);
    let visible=0;visibleIds=[];
    const visibleActions=new Set(),onScreen=new Set();
    for(let row=first;row<last;row++)for(let col=0;col<cols;col++){
      const i=row*cols+col;if(i>=list.length)break;
      const x=col*CW,y=row*CH;if(x*scale+panX>width||(x+CW)*scale+panX<0)continue;
      const frame=list[i];onScreen.add(frame.id);
      const sx=x*scale+panX,sy=y*scale+panY,sw=(CW-14)*scale,sh=(CH-14)*scale;
      // Do not batch a card when only a thin, unreadable sliver is on screen.
      const area=Math.max(0,Math.min(width,sx+sw)-Math.max(0,sx))*Math.max(0,Math.min(height,sy+sh)-Math.max(0,sy));
      if(area>=sw*sh*.3){visible++;visibleIds.push(...entryIds(frame));}
      if(viewMode==='sequences'){drawSequence(frame,i,x,y,visibleActions);continue;}
      const review=cardReview(frame),accent=review.priority===2?'#ff6969':review.priority===1?'#eac264':auditInfo(frame)?.passed?'#77ce98':'#aaaaaa';
      ctx.fillStyle='#191919';ctx.fillRect(x,y,CW-14,CH-14);ctx.strokeStyle=i===selected?'#777777':'#333333';ctx.lineWidth=1;ctx.strokeRect(x+.5,y+.5,CW-15,CH-15);
      text(frame.name,x+12,y+21,CW-40,'#e4e8ed',12);
      const job=imageLabAssetJobs.get(frame.id),approved=!imageLabNeedsApproval(frame)&&imageLabApprovals[frame.id];
      const tracked=trackedEntry(frame),trackedState=tracked&&SpriteBatches.state(tracked);
      const result=trackedState==='ready'?tracked.job:null;
      picture(request(frame,false,result),x+8,y+30,CW-30,130,false);
      const pending=job&&['queued','running'].includes(job.status);
      const badge=tracked?batchLabels[trackedState].toUpperCase():pending?(job.status==='queued'?'EN COLA':'GENERANDO'):approved?'✓ APROBADO':job&&['failed','interrupted'].includes(job.status)?'ERROR · ABRIR':job?.status==='ready'?'LISTO · REVISAR':frame.edited?'✓ VERSIÓN EN USO':null;
      if(badge){const color=tracked?batchColors[trackedState]:pending?'#73adff':approved?'#77ce98':job&&['failed','interrupted'].includes(job.status)?'#ff6969':'#eac264';ctx.strokeStyle=color;ctx.lineWidth=2;ctx.strokeRect(x+1,y+1,CW-16,CH-16);ctx.fillStyle='#141414';ctx.fillRect(x+8,y+140,CW-30,20);text(badge,x+12,y+154,CW-38,color,9);}
      if(picked.has(frame.id)){ctx.strokeStyle='#ffffff';ctx.lineWidth=3;ctx.strokeRect(x-3,y-3,CW-8,CH-8);}
      let selectButton=selectionButtons.get(frame.id);
      if(!selectButton){
        selectButton=ReviewUI.button('Seleccionar asset: '+frame.name,'check',e=>pick(items.findIndex(f=>f.id===frame.id),e.shiftKey),'ab-select-card');
        selectButton.setAttribute('role','checkbox');selectButton.dataset.assetId=frame.id;
        actionLayer.append(selectButton);selectionButtons.set(frame.id,selectButton);
      }
      selectButton.setAttribute('aria-checked',String(picked.has(frame.id)));
      selectButton.style.transform=`translate(${(x+CW-24)*scale+panX-28}px,${(y+36)*scale+panY}px)`;
      ctx.fillStyle=accent;ctx.beginPath();ctx.arc(x+12,y+174,3,0,Math.PI*2);ctx.fill();
      text(tracked?.error||tracked?.job?.error||(result?'Resultado de esta tanda':review.text),x+21,y+178,CW-43,trackedState==='error'?'#ff6969':accent,10);
      const similarityValue=similarity(auditInfo(frame));
      text(similarityValue===null?'Sin análisis vigente':`${similarityValue}% similitud estimada`,x+10,y+195,CW-36,'#dddddd',11);
      if(scale>=.5){
        visibleActions.add(frame.id);
        let buttons=actions.get(frame.id);
        if(!buttons){
          buttons=document.createElement('div');buttons.className='ab-card-actions';
          const reviewButton=document.createElement('button');reviewButton.className='ab-review';reviewButton.textContent='Comparar y crear versiones';reviewButton.setAttribute('aria-label','Comparar asset: '+frame.name);
          reviewButton.textContent='Abrir';reviewButton.onclick=()=>edit(items.findIndex(f=>f.id===frame.id));
          const approveButton=document.createElement('button');approveButton.className='ab-approve';
          approveButton.onclick=async()=>{approveButton.disabled=true;try{const f=state.frames.find(f=>f.id===frame.id),e=trackedEntry(f);if(e?.job?.image){const info=await api('/api/open?id='+f.id);let revision=info.revision;if(info.current_sha256!==e.job.candidate_sha256)revision=(await api('/api/variants/select',{job_id:e.job.id,revision})).revision;await api('/api/imagelab/approve',{id:f.id,revision});await SequenceTools.refreshAssets([f.id]);}else await approveImageLabAsset(f);}catch(error){imageLabNotice(error.message);}finally{approveButton.disabled=false;updateBatchControls();invalidate();}};
          const auditButton=document.createElement('button');auditButton.className='ab-audit';auditButton.textContent='↻';auditButton.title='Volver a analizar';auditButton.onclick=()=>analyze([frame.id]);auditButton.setAttribute('aria-label','Analizar asset: '+frame.name);
          buttons.append(reviewButton,approveButton,auditButton);actionLayer.append(buttons);actions.set(frame.id,buttons);
        }
        const approveButton=buttons.querySelector('.ab-approve');
        buttons.querySelector('.ab-review').setAttribute('aria-label','Comparar asset: '+frame.name+(badge?' · '+badge:''));
        approveButton.textContent=approved?'Aprobado':'Aprobar';
        approveButton.setAttribute('aria-label',(approved?'Aprobado: ':'Aplicar y aprobar última versión: ')+frame.name);
        approveButton.title='Aplica y aprueba la última generación terminada. Conserva el historial.';
        approveButton.setAttribute('aria-pressed',String(!!approved));
        approveButton.disabled=!!tracked&&['pending','queued','running','error'].includes(trackedState);
        buttons.querySelector('.ab-audit').disabled=!!auditProgress.running;
        const report=auditInfo(frame);
        buttons.title=report?(report.issues.join('\n')||'Sin desvíos detectados')+'\nSimilitud estimada: '+similarity(report)+'%\n'+Object.entries(report.metrics||{}).map(([key,value])=>key+': '+value).join(' · ')+'\nResultado reducido al tamaño original. No mide calidad artística.':auditResults[frame.id]?.error||'Sin análisis vigente';
        buttons.style.transform=`translate(${x*scale+panX+8*scale}px,${(y+207)*scale+panY}px) scale(${scale})`;
      }
    }
    for(const [id,buttons] of actions)if(!visibleActions.has(id)){buttons.remove();actions.delete(id);}
    for(const [id,button] of selectionButtons)if(!onScreen.has(id)){button.remove();selectionButtons.delete(id);}
    ctx.restore();pump();zoomLabel.textContent=Math.round(scale*100)+'%';
    if(!items.length&&!sequences.length){
      if(!state.catalogLoaded){
        text('Cargando assets…',30,60,width-60,'#bac4d0',16);
        // Animated loading bar
        const barW=Math.min(400,width-60),barH=4,barX=30,barY=85;
        ctx.fillStyle='#2a2d32';ctx.fillRect(barX,barY,barW,barH);
        const pulse=(Date.now()%2000)/2000,pw=barW*.3;
        ctx.fillStyle='#c4db9e';ctx.fillRect(barX+pulse*(barW+pw)-pw,barY,pw,barH);
        setTimeout(invalidate,50);
      }else{
        text('No hay assets con estos filtros.',30,60,width-60,'#bac4d0',16);
      }
    }
    statusLine.textContent=list.length+(viewMode==='sequences'?' secuencias':' assets')+' · '+visible+' visibles'+(selectionMode?` · ${picked.size} cuadros seleccionados · Shift: rango · Ctrl+A: listado`:selected>=0&&list[selected]?' · '+list[selected].name:' · clic para comparar · arrastrar para mover · Ctrl + rueda para zoom');
    updateSelectionBar();
  }
  function resize(){const rect=canvas.getBoundingClientRect();if(rect.width<=36||rect.height<=0)return;width=rect.width;height=rect.height;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);if(!Number.isFinite(scale)||scale<=0)fit();invalidate();}
  function fit(){if(width<=36||height<=0)return;CW=viewMode==='sequences'?240:210;CH=viewMode==='sequences'?280:258;cols=Math.max(1,Math.min(12,Math.floor(width/Number(panel.querySelector('[data-density]').value))));scale=Math.max(.25,Math.min(1.25,(width-36)/(cols*CW)));panX=18;panY=18;invalidate();}
  function zoom(factor,x=width/2,y=height/2){const previous=scale;scale=Math.max(.25,Math.min(3,scale*factor));panX=x-(x-panX)*scale/previous;panY=y-(y-panY)*scale/previous;invalidate();}
  function rebuild(preserveView=false){
    CW=viewMode==='sequences'?240:210;CH=viewMode==='sequences'?280:258;
    if(preserveView?.target&&sequenceFilters().includes(preserveView.target))batchFilter=null;
    const focused=entries()[selected]?.id,known=new Set(state.frames.map(f=>f.id));
    for(const id of picked)if(!known.has(id))picked.delete(id);
    const term=search.value.trim().toLowerCase();
    items=state.frames.filter(f=>(!collection.value||f.category===collection.value)&&(!term||(f.name+' '+f.category).toLowerCase().includes(term))&&
      (filter.value==='all'||filter.value==='issues'&&cardReview(f).priority>0||filter.value==='audit'&&auditInfo(f)?.passed===false||filter.value==='approved'&&imageLabApprovals[f.id]||filter.value==='rejected'&&reviewInfo(f).priority===2||filter.value==='unreviewed'&&!auditInfo(f)||filter.value==='edited'&&f.edited));
    const silhouette=f=>f.review?.current&&Number.isFinite(f.review.validation?.silhouette_iou)?f.review.validation.silhouette_iou:2;
    const problem=panel.querySelector('[data-problem]').value;
    const maximum=Number(panel.querySelector('[data-similarity]').value);
    items=items.filter(f=>(!problem||auditInfo(f)?.issues?.includes(problem))&&(maximum===100||similarity(auditInfo(f))!==null&&similarity(auditInfo(f))<=maximum));
    const edgeFilter=panel.querySelector('[data-edge-filter]').value;
    if(edgeFilter!=='all')items=items.filter(f=>edgeState(f)===edgeFilter);
    items.sort((a,b)=>order.value==='similarity'?(similarity(auditInfo(a))??101)-(similarity(auditInfo(b))??101):order.value==='priority'?(cardReview(b).priority-cardReview(a).priority||(auditInfo(b)?.score||0)-(auditInfo(a)?.score||0)||silhouette(a)-silhouette(b)||a.group.localeCompare(b.group)||a.number-b.number):(a.group.localeCompare(b.group)||a.number-b.number));
    sequences=SequenceTools.groups(state.frames,items);
    if(sequenceScope)items=items.filter(f=>SequenceTools.key(f)===sequenceScope).sort((a,b)=>a.number-b.number);
if(batchFilter){const batch=SpriteBatches.get(batchId);if(batch){const ids=new Set(batch.entries.filter(e=>batchFilter==='all'||SpriteBatches.state(e)===batchFilter).map(e=>e.asset_id));items=state.frames.filter(f=>ids.has(f.id)).sort((a,b)=>a.group.localeCompare(b.group)||a.number-b.number);}else batchFilter=null;}
    renderBatchBar();
    updateViewControls();updateBatchControls();selected=entries().findIndex(f=>f.id===focused);if(preserveView!==true)panY=18;invalidate();
  }
  function hit(x,y){const wx=(x-panX)/scale,wy=(y-panY)/scale;if(wx<0||wy<0)return -1;const col=Math.floor(wx/CW),row=Math.floor(wy/CH);if(col>=cols||wx%CW>CW-14||wy%CH>CH-14)return -1;const i=row*cols+col;return i<entries().length?i:-1;}
  function edit(index){
    const entry=entries()[index];if(!entry)return;selected=index;invalidate();
    if(viewMode==='sequences'){if(entry.frames&&entry.frames.length===1){rememberView();openGridReview(entry.frames[0].id,[entry.frames[0].id]);return;}openSequence(entry);return;}
    rememberView();
    openGridReview(entry.id,items.map(f=>f.id));
  }
  function openGridReview(id,ids){const frame=state.frames.find(f=>f.id===id);if(!frame)return;const tracked=trackedEntry(frame);const job=tracked?.job||imageLabAssetJobs.get(id);openAssetReview(frame,job?.id||null,null,{embedded:true,ids,navigate:next=>openGridReview(next,ids),onClose:()=>{panel.hidden=false;panel.inert=false;active=true;canvas.focus({preventScroll:true});invalidate();LiveAssets.request(ids);}}).catch(e=>imageLabNotice(e.message));}

  function create(){
    panel=document.createElement('section');panel.className='asset-browser';
    panel.innerHTML='<div class="ab-header"><div><strong>ASSETS</strong><small>Original y remaster · mesa de revisión</small></div><input data-search type="search" placeholder="Buscar personaje, traje, cuadro…" aria-label="Buscar assets"><select data-collection aria-label="Colección de assets"></select><select data-filter aria-label="Estado de revisión"><option value="all">Todos los estados</option><option value="issues">Necesitan revisión</option><option value="rejected">Rechazados</option><option value="unreviewed">Sin evaluación</option><option value="edited">Con retoque</option></select><select data-order aria-label="Orden de assets"><option value="priority">Problemas primero</option><option value="name">Orden de secuencia</option></select><button data-close>Volver al taller</button></div><div class="ab-tools"><span>Rojo: rechazo registrado · ámbar: revisar · gris: sin alerta registrada</span><button data-minus aria-label="Alejar">−</button><output data-zoom></output><button data-plus aria-label="Acercar">+</button><button data-fit>Encuadrar</button></div><canvas tabindex="0" aria-label="Mesa de assets. Arrastrar para desplazar, Ctrl más rueda para zoom. Flechas para seleccionar y Enter para comparar."></canvas><div class="ab-status" role="status"></div>';
    document.body.append(panel);canvas=panel.querySelector('canvas');
    const deliveryButton=document.createElement('button');deliveryButton.textContent='Entregas';deliveryButton.onclick=showDeliveries;panel.querySelector('.ab-header').append(deliveryButton);
    const globalPR=document.createElement('button');globalPR.className='accent ab-global-pr';globalPR.textContent='Enviar PR con aprobados';globalPR.onclick=()=>{const ids=state.frames.filter(f=>imageLabApprovals[f.id]).map(f=>f.id);if(ids.length)showSelectionPR(ids);else imageLabNotice('No hay cuadros aprobados todavía.');};panel.querySelector('.ab-header').append(globalPR);
    const queueButton=document.createElement('button');queueButton.textContent='Cola de trabajos';queueButton.dataset.imagelabQueue='';queueButton.onclick=showImageLabQueue;panel.querySelector('.ab-tools').append(queueButton);
    panel.querySelector('.ab-header small').textContent='Resultados · mesa de revisión';
    panel.querySelector('.ab-tools span').textContent='Arrastrá para mover · Ctrl + rueda para zoom';
    const density=document.createElement('select');density.dataset.density='';density.setAttribute('aria-label','Densidad de assets');density.innerHTML='<option value="170">Compacta</option><option value="210" selected>Normal</option><option value="290">Grande</option>';density.onchange=fit;panel.querySelector('.ab-tools').prepend(density);
    const stage=document.createElement('div');stage.className='ab-stage';canvas.replaceWith(stage);stage.append(canvas);actionLayer=document.createElement('div');actionLayer.className='ab-actions';stage.append(actionLayer);
    const viewSwitch=document.createElement('div');viewSwitch.className='ab-view-switch';viewSwitch.setAttribute('aria-label','Vista del explorador');
    for(const [mode,label,icon] of [['assets','Assets','grid-2x2'],['sequences','Secuencias','layers']]){
      const button=ReviewUI.button(label,icon,()=>setView(mode),'');button.dataset.view=mode;button.append(document.createTextNode(label));viewSwitch.append(button);
    }
    panel.querySelector('.ab-header strong').parentElement.replaceWith(viewSwitch);
    const path=document.createElement('div');path.className='ab-sequence-path';path.hidden=true;
    const back=ReviewUI.button('Volver a secuencias','arrow-left',()=>setView('sequences'),'');back.append(document.createTextNode('Secuencias'));
    const name=document.createElement('span'),mark=document.createElement('button');name.dataset.sequenceTitle='';mark.textContent='Marcar secuencia completa';mark.onclick=()=>pickMany(state.frames.filter(f=>SequenceTools.key(f)===sequenceScope).map(f=>f.id));path.append(back,name,mark);stage.before(path);
    const note=document.createElement('small');note.dataset.sequenceNote='';note.className='ab-sequence-note';note.hidden=true;note.textContent='Por traje o recurso · marcar una secuencia incluye todos sus cuadros, aunque el filtro oculte algunos.';stage.before(note);
    ctx=canvas.getContext('2d');search=panel.querySelector('[data-search]');collection=panel.querySelector('[data-collection]');filter=panel.querySelector('[data-filter]');order=panel.querySelector('[data-order]');zoomLabel=panel.querySelector('[data-zoom]');statusLine=panel.querySelector('.ab-status');
    order.title='Rechazos primero; luego borradores. Dentro de cada estado, menor coincidencia de silueta si hay una medición registrada.';
    filter.add(new Option('Desvíos automáticos','audit'));filter.add(new Option('Aprobados','approved'));
    const controls=document.createElement('div');controls.className='ab-audit-tools';
    controls.innerHTML='<strong>Control visual</strong><button data-audit-run data-audit-filtered>Analizar listado</button><button data-audit-run data-audit-all>Analizar todos</button><label><input type="checkbox" data-audit-strict> Más sensible</label><span data-audit-status role="status">Comparación local con el original · sin créditos</span><button data-audit-problems>Ver problemas</button>';
    stage.before(controls);
    order.add(new Option('Menor similitud','similarity'));
    const bulk=document.createElement('div');bulk.className='ab-audit-tools ab-bulk-tools';
    bulk.innerHTML=`<label>Problema <select data-problem aria-label="Filtrar por problema"><option value="">Todos</option>${['Posible halo claro','Borde/alpha desviado','Trazo oscuro alterado','Forma desviada','Color desviado','Proporciones diferentes'].map(p=>'<option>'+p+'</option>').join('')}</select></label>
      <label>Similitud ≤ <input data-similarity type="number" min="0" max="100" value="100"> %</label>
      <label>Aplicar a <select data-batch-scope><option value="selected" hidden>Assets seleccionados</option><option value="filtered" selected>Listado filtrado</option><option value="collection">Colección actual</option><option value="all">Todos los assets</option></select></label>
      <label>Tratamiento <select data-treatment><option value="halo">Oscurecer halo · sin recorte</option><option value="soft">Limpiar borde · suave</option><option value="trim">Solo recortar</option><option value="custom">Personalizado</option></select></label>
      <label>Recortar <input data-batch-trim type="number" min="0" max="3" step="0.25" value="0.5"> px</label>
      <label>Tinte oscuro <input data-batch-tint type="number" min="0" max="100" step="10" value="70"> %</label>
      <label><input data-batch-dark type="checkbox" checked> Proteger tinta</label>
      <label title="Conserva cortes rectos detectados en el original; detección aproximada."><input data-batch-seams type="checkbox" checked> Proteger empalmes</label>
      <label><input data-skip-approved type="checkbox" checked> Omitir aprobados</label>
      <button data-batch-approve title="Aprueba las versiones actualmente en uso como referencias. No aplica propuestas pendientes.">Aprobar lote</button><button data-batch>Limpiar filtrados</button><button data-batch-stop hidden>Detener envío</button>
      <small data-batch-status role="status">Local · sin créditos · versiones sin aplicar. Con protección de empalmes se omiten assets sin original. Similitud estimada, no calidad artística.</small>`;
    const batchSettings=document.createElement('details');batchSettings.className='ab-batch-settings';
    const batchSummary=document.createElement('summary');batchSummary.textContent='Acciones por lote · aprobar y limpiar';batchSettings.append(batchSummary,bulk);controls.after(batchSettings);
    const batchTargetsRow=document.createElement('div');batchTargetsRow.className='ab-batch-targets';
    batchTargetsRow.append(bulk.querySelector('[data-batch-scope]').parentElement,bulk.querySelector('[data-skip-approved]').parentElement,bulk.querySelector('[data-batch-approve]'));
    bulk.prepend(batchTargetsRow);
    // Keep discovery filters visible; fold only the treatment controls.
    const problemLabel=bulk.querySelector('[data-problem]').parentElement;
    const similarityLabel=bulk.querySelector('[data-similarity]').parentElement;
    controls.append(problemLabel,similarityLabel);
    const presetLabel=document.createElement('label');presetLabel.innerHTML='Vista <select data-preset aria-label="Preset de problemas"><option value="all">Todos</option><option value="halo">Halos claros</option><option value="edge">Bordes / alpha</option><option value="ink">Trazo alterado</option><option value="shape">Forma desviada</option><option value="color">Color desviado</option><option value="pending">Sin analizar</option><option value="approved">Aprobados</option><option value="custom">Personalizada</option></select>';
    controls.prepend(presetLabel);
    const edgeLabel=document.createElement('label');edgeLabel.innerHTML='Bordes <select data-edge-filter><option value="all">Todos</option><option value="none">Sin limpiar</option><option value="applied">Limpieza aplicada</option><option value="prepared">Limpieza en cola / para revisar</option></select>';controls.append(edgeLabel);edgeLabel.querySelector('select').onchange=rebuild;
    const quick=document.createElement('div');quick.className='ab-quick-actions';
    quick.innerHTML='<button data-clean-auto>Limpiar bordes · automático</button><button data-redo>Rehacer desviados</button><select data-redo-model aria-label="Modelo para rehacer"><option>Real-ESRGAN Anime 6B</option><option>Wonder 3.5 High + Bria</option><option>CGI</option></select><small>Limpiar: local, omite limpiezas existentes. Rehacer: listado con desvío ≥ 2× el umbral, desde original; consume créditos. Crea versiones para revisar.</small><p data-quick-status role="status"></p>';
    controls.after(quick);quick.append(panel.querySelector('[data-batch-status]'));
    const selectionBar=document.createElement('div');selectionBar.className='ab-selection-bar';
    selectionBar.innerHTML='<button data-selection-mode aria-pressed="false"><span>Seleccionar</span></button><output data-selection-count aria-live="polite"></output><div class="ab-selection-options"><button data-select-visible title="Sumar los assets que se ven ahora en el canvas">Visibles</button><button data-select-all title="Sumar todo el listado filtrado · Ctrl+A">Todo el listado</button><button data-selection-clear disabled>Quitar selección</button></div>';
    selectionBar.querySelector('[data-selection-mode]').prepend(ReviewUI.icon('check'));
    quick.before(selectionBar);
    selectionBar.querySelector('[data-selection-mode]').onclick=()=>{if(selectionMode)clearSelection(true);else{selectionMode=true;selectionChanged();}};
    selectionBar.querySelector('[data-select-visible]').onclick=()=>pickMany(visibleIds);
    selectionBar.querySelector('[data-select-all]').onclick=()=>pickMany(listedIds());
    selectionBar.querySelector('[data-selection-clear]').onclick=()=>clearSelection();
    const waterButton=ReviewUI.button('Seleccionar animaciones del mar','layers',()=>{
      const frames=SequenceTools.waterFrames(state.frames);if(!frames.length){imageLabNotice('No hay cuadros de agua en el catálogo.');return;}
      clearSelection();sequenceScope=null;sequenceReturn=null;viewMode='sequences';search.value='';collection.value=frames[0].category;filter.value='all';order.value='name';
      panel.querySelector('[data-problem]').value='';panel.querySelector('[data-similarity]').value='100';panel.querySelector('[data-edge-filter]').value='all';panel.querySelector('[data-preset]').value='all';
      rebuild();pickMany(frames.map(f=>f.id));fit();
    },'');waterButton.append(document.createTextNode('Animaciones del mar'));selectionBar.querySelector('.ab-selection-options').prepend(waterButton);
    canvas.setAttribute('aria-label','Mesa de assets. Arrastrar para desplazar. Casillas o Ctrl+clic para seleccionar; Shift para un rango. Flechas para recorrer, espacio para marcar, Enter para comparar.');
    // Both batch actions keep progress visible, even with advanced controls folded.
    const batchStatus=quick.querySelector('[data-batch-status]');batchStatus.textContent='';
    quick.querySelector('[data-clean-auto]').onclick=()=>{
      if(batchSending)return;if(!selectionMode)bulk.querySelector('[data-batch-scope]').value='filtered';bulk.querySelector('[data-batch-trim]').value='.5';bulk.querySelector('[data-batch-tint]').value='70';bulk.querySelector('[data-batch-seams]').checked=true;bulk.querySelector('[data-batch-dark]').checked=true;bulk.querySelector('[data-skip-approved]').checked=true;updateBatchControls();bulk.querySelector('[data-batch]').click();
    };
    quick.querySelector('[data-redo]').onclick=async()=>{
      if(batchSending)return;const targets=actionCandidates().filter(f=>f.has_reference&&!imageLabApprovals[f.id]&&auditInfo(f)?.score>=2).slice();if(!targets.length)return;
      const model=panel.querySelector('[data-redo-model]').value;batchSending=true;batchStop=false;let sent=0;const errors=[];
      updateBatchControls();
      panel.querySelector('[data-batch-stop]').hidden=false;
      try{for(const f of targets){if(batchStop)break;batchStatus.textContent=`Rehaciendo ${sent+errors.length+1}/${targets.length}`;try{await api('/api/upscale/jobs',{id:f.id,enhance_model:model});sent++;}catch(e){errors.push(f.name+': '+e.message);}}}
      finally{batchSending=false;panel.querySelector('[data-batch-stop]').hidden=true;batchStatus.textContent=`${sent} enviados · ${errors.length} errores${batchStop?' · detenido':''}`;batchStatus.title=errors.join('\n');updateBatchControls();}
    };
    quick.append(panel.querySelector('[data-batch-stop]'));
    const selectionActions=document.createElement('div');selectionActions.className='ab-selection-actions';
    for(const [key,label,icon] of [['wonder','Generar · Wonder ×4 → Bria','wand-sparkles'],['source','Quitar agua / colores','pipette'],['apply','Aplicar resultados','check'],['bria','Alpha','scan-line'],['clean','Bordes','scissors'],['upscale','Avanzado','sliders-horizontal'],['pr','Crear PR','upload']]){
      const button=ReviewUI.button(label,icon,()=>processSelection(key),'');button.dataset.selectionAction=key;button.append(document.createTextNode(label));button.hidden=true;
      if(key==='wonder'){button.className='accent';button.title='Generar selección desde los originales · Wonder ×4 y Bria · consume créditos';}
      selectionActions.append(button);
    }
    quick.prepend(selectionActions);
    presetLabel.querySelector('select').onchange=e=>{
      const key=e.target.value;if(key==='custom')return;
      panel.querySelector('[data-edge-filter]').value=key==='cleaned'?'applied':key==='unclean'?'none':'all';
      search.value='';filter.value=key==='pending'?'unreviewed':key==='approved'?'approved':'all';
      panel.querySelector('[data-problem]').value=({halo:'Posible halo claro',edge:'Borde/alpha desviado',ink:'Trazo oscuro alterado',shape:'Forma desviada',color:'Color desviado'})[key]||'';
      panel.querySelector('[data-similarity]').value='100';rebuild();
    };
    bulk.querySelector('[data-batch-trim]').value='0';
    bulk.querySelector('[data-batch-scope]').onchange=updateBatchControls;
    bulk.querySelector('[data-treatment]').onchange=e=>{
      const values={halo:[0,70],soft:[.5,70],trim:[.5,0]}[e.target.value];if(!values)return;
      bulk.querySelector('[data-batch-trim]').value=values[0];bulk.querySelector('[data-batch-tint]').value=values[1];
      bulk.querySelector('[data-batch-seams]').checked=true;bulk.querySelector('[data-batch-dark]').checked=true;rebuild();
    };
    for(const el of bulk.querySelectorAll('input:not([data-skip-approved])'))el.oninput=()=>{bulk.querySelector('[data-treatment]').value='custom';rebuild();};
    for(const selector of ['[data-problem]','[data-similarity]','[data-skip-approved]'])panel.querySelector(selector).onchange=()=>{if(selector!=='[data-skip-approved]')panel.querySelector('[data-preset]').value='custom';rebuild();};
    panel.querySelector('[data-batch-stop]').onclick=()=>{batchStop=true;};
    bulk.querySelector('[data-batch-approve]').onclick=async()=>{
      if(batchSending)return;
      const targets=batchTargets(true).map(f=>({id:f.id,revision:f.revision,name:f.name}));
      if(!targets.length)return;
      batchSending=true;batchStop=false;
      updateBatchControls();
      for(const b of bulk.querySelectorAll('[data-batch],[data-batch-approve]'))b.disabled=true;
      panel.querySelector('[data-batch-stop]').hidden=false;
      const label=panel.querySelector('[data-batch-status]');let approved=0;const errors=[];
      try{for(const frame of targets){
        if(batchStop)break;
        label.textContent=`Aplicando y aprobando ${approved+errors.length+1}/${targets.length} · última generación`;
        try{await acceptLatestImageLabResult(frame);approved++;invalidate();}
        catch(error){errors.push(frame.name+': '+error.message);}
      }}finally{
        batchSending=false;for(const b of bulk.querySelectorAll('[data-batch],[data-batch-approve]'))b.disabled=false;
        panel.querySelector('[data-batch-stop]').hidden=true;
        label.textContent=`${approved} aplicados y aprobados · ${errors.length} errores${batchStop?' · detenido':''}. Últimas generaciones en uso.`;
        label.title=errors.join('\n');updateBatchControls();window.dispatchEvent(new Event('imagelab-assets'));
      }
    };
    bulk.querySelector('[data-batch]').onclick=async()=>{
      if(batchSending)return;
      const targets=batchTargets().map(f=>({id:f.id,revision:f.revision,name:f.name}));
      const settings={trim_pixels:Number(bulk.querySelector('[data-batch-trim]').value),tint_strength:Number(bulk.querySelector('[data-batch-tint]').value)/100,protect_dark:bulk.querySelector('[data-batch-dark]').checked,protect_seams:bulk.querySelector('[data-batch-seams]').checked};
      if(![...bulk.querySelectorAll('input[type=number]')].every(el=>el.reportValidity())||!targets.length)return;
      batchSending=true;batchStop=false;bulk.querySelector('[data-batch]').disabled=true;panel.querySelector('[data-batch-stop]').hidden=false;
      updateBatchControls();
      bulk.querySelector('[data-batch-approve]').disabled=true;
      let sent=0;const failures=[];const label=panel.querySelector('[data-batch-status]');
      try{for(const f of targets){
        if(batchStop)break;
        label.textContent=`Enviando ${sent+failures.length+1}/${targets.length} · ${sent} encolados`;
        try{await api('/api/variants/refine-alpha',{id:f.id,revision:f.revision,...settings});sent++;}
        catch(error){failures.push(f.name+': '+error.message);}
      }}finally{
        batchSending=false;bulk.querySelector('[data-batch]').disabled=false;panel.querySelector('[data-batch-stop]').hidden=true;
        bulk.querySelector('[data-batch-approve]').disabled=false;
        label.textContent=`${sent} enviados · ${failures.length} errores${batchStop?' · envío detenido':''}. Revisá las versiones en la cola.`;
        label.title=failures.join('\n');window.dispatchEvent(new Event('imagelab-assets'));invalidate();
      }
    };
    controls.querySelector('[data-audit-filtered]').onclick=()=>analyze(actionCandidates().map(f=>f.id));
    controls.querySelector('[data-audit-all]').onclick=()=>analyze(state.frames.map(f=>f.id));
    controls.querySelector('[data-audit-problems]').onclick=()=>{filter.value='audit';rebuild();};
    search.oninput=rebuild;collection.onchange=rebuild;filter.onchange=rebuild;order.onchange=rebuild;
    panel.querySelector('[data-close]').onclick=()=>{panel.hidden=true;active=false;};panel.querySelector('[data-minus]').onclick=()=>zoom(1/1.2);panel.querySelector('[data-plus]').onclick=()=>zoom(1.2);panel.querySelector('[data-fit]').onclick=fit;
    canvas.onpointerdown=e=>{if(e.button!==0&&e.button!==1)return;canvas.focus();canvas.setPointerCapture(e.pointerId);drag={id:e.pointerId,x:e.offsetX,y:e.offsetY,lastX:e.offsetX,lastY:e.offsetY,moved:false};};
    canvas.onpointermove=e=>{if(!drag)return;const dx=e.offsetX-drag.lastX,dy=e.offsetY-drag.lastY;if(Math.hypot(e.offsetX-drag.x,e.offsetY-drag.y)>5)drag.moved=true;if(drag.moved){panX+=dx;panY+=dy;invalidate();}drag.lastX=e.offsetX;drag.lastY=e.offsetY;};
    canvas.onpointerup=e=>{if(!drag)return;const tap=!drag.moved;drag=null;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);if(tap&&e.button===0){const index=hit(e.offsetX,e.offsetY);if(selectionMode||e.ctrlKey||e.metaKey||e.shiftKey)pick(index,e.shiftKey);else edit(index);}};canvas.onpointercancel=()=>{drag=null;};
    canvas.addEventListener('wheel',e=>{e.preventDefault();if(e.ctrlKey||e.metaKey)zoom(Math.exp(-e.deltaY*.002),e.offsetX,e.offsetY);else{panX-=e.deltaX;panY-=e.deltaY;invalidate();}},{passive:false});
    canvas.onkeydown=e=>{
      if(e.key==='Enter'){e.preventDefault();edit(selected);return;}
      if(e.key===' '){e.preventDefault();e.stopPropagation();pick(selected<0?0:selected,e.shiftKey);return;}
      const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-cols,ArrowDown:cols}[e.key];
      if(delta!=null&&entries().length){e.preventDefault();e.stopPropagation();const before=selected;selected=Math.max(0,Math.min(entries().length-1,selected<0?0:selected+delta));if(e.shiftKey){if(!selectionAnchor)selectionAnchor=entries()[Math.max(0,before)].id;pick(selected,true);}panY=height/2-(Math.floor(selected/cols)*CH+CH/2)*scale;invalidate();}
    };
    panel.addEventListener('keydown',e=>{
      if(e.target.closest('input,textarea,select,[contenteditable=true]'))return;
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){e.preventDefault();e.stopPropagation();pickMany(listedIds());}
      if(e.key==='Escape'&&selectionMode){e.preventDefault();e.stopPropagation();clearSelection(true);}
    });
    panel.classList.add('ab-simple');
    const drawer=document.createElement('aside');drawer.className='ab-settings-drawer';drawer.hidden=true;drawer.setAttribute('aria-label','Ajustes del explorador');
    const shade=document.createElement('div');shade.className='ab-settings-shade';shade.hidden=true;
    const drawerHead=document.createElement('div');drawerHead.className='ab-drawer-head';drawerHead.innerHTML='<strong>Ajustes</strong><button aria-label="Cerrar ajustes">Cerrar</button>';
    drawer.append(drawerHead);panel.append(shade,drawer);
    const settingsButton=document.createElement('button');settingsButton.textContent='Ajustes';settingsButton.dataset.settingsToggle='';settingsButton.setAttribute('aria-expanded','false');
    const toggleSettings=open=>{drawer.hidden=shade.hidden=!open;settingsButton.setAttribute('aria-expanded',String(open));if(open)drawerHead.querySelector('button').focus();else settingsButton.focus();};
    settingsButton.onclick=()=>toggleSettings(drawer.hidden);drawerHead.querySelector('button').onclick=()=>toggleSettings(false);shade.onclick=()=>toggleSettings(false);
    drawer.onkeydown=e=>{if(e.key==='Escape'){e.stopPropagation();toggleSettings(false);}};
    const section=(title,...nodes)=>{const block=document.createElement('section');const heading=document.createElement('h2');heading.textContent=title;block.append(heading,...nodes);drawer.append(block);};
    const header=panel.querySelector('.ab-header');
    presetLabel.querySelector('select').add(new Option('Bordes sin limpiar','unclean'));presetLabel.querySelector('select').add(new Option('Bordes limpiados','cleaned'));
    header.insertBefore(presetLabel,header.querySelector('[data-close]'));
    header.insertBefore(queueButton,header.querySelector('[data-close]'));
    header.insertBefore(settingsButton,header.querySelector('[data-close]'));
    header.querySelector('[data-close]').remove();
    section('Organizar',filter,order,density);
    section('Control visual',controls);
    const modelControl=quick.querySelector('[data-redo-model]');section('Modelo para rehacer',modelControl);
    const modelHelp=document.createElement('p');modelHelp.textContent='Rehacer usa el original y consume créditos. Solo toma desvíos mayores a 2× el umbral.';drawer.lastElementChild.append(modelHelp);
    batchSettings.remove();section('Limpieza personalizada y aprobación',bulk);
    quick.querySelector('small').remove();quick.querySelector('[data-quick-status]').remove();
    quick.querySelector('[data-clean-auto]').textContent='Limpiar bordes';
    quick.querySelector('[data-clean-auto]').title='Listado actual · recorte 0,5 px y tinte 70% · protege empalmes · omite aprobados y limpiezas existentes';
    quick.querySelector('[data-redo]').title='Rehacer desvíos graves desde el original · consume créditos · modelo en Ajustes';
    const approveList=document.createElement('button');approveList.dataset.approveVisible='';approveList.textContent='Aprobar listado';approveList.onclick=()=>{if(batchSending)return;if(!selectionMode)bulk.querySelector('[data-batch-scope]').value='filtered';updateBatchControls();bulk.querySelector('[data-batch-approve]').click();};
    quick.insertBefore(approveList,batchStatus);
    const actionHint=document.createElement('span');actionHint.className='ab-action-hint';actionHint.textContent='Listado actual · Rehacer consume créditos';quick.insertBefore(actionHint,batchStatus);
    const tools=panel.querySelector('.ab-tools');tools.querySelector('span').remove();
    const bottom=document.createElement('div');bottom.className='ab-footer';statusLine.replaceWith(bottom);bottom.append(statusLine,tools);
    createBatchBar(stage);new ResizeObserver(resize).observe(canvas);
  }
  async function open({focusId=null}={}){
    if(confiteSession)return;
    const returning=!!panel, previousView=returning?snapshotView():savedView();
    if(!panel)create();panel.hidden=false;active=true;statusLine.textContent='Cargando assets…';
    viewReady=false;
    resize();invalidate();
    if(!state.catalogLoaded)await catalog();
    refreshAudit().catch(()=>{});
    if(state.info){const key=state.info.frame.id+'/edit';cache.get(key)?.close?.();cache.delete(key);diskCache.then(s=>s&&s.keys().then(keys=>keys.filter(k=>k.url.includes(state.info.frame.id)).forEach(k=>s.delete(k)))).catch(()=>{});}
    const previous=collection.value;const categories=[...new Set(state.frames.map(f=>f.category))].sort();
    collection.replaceChildren(new Option('⚠ Todas ('+state.frames.length+' assets)',''));categories.forEach(c=>{const count=state.frames.filter(f=>f.category===c).length;collection.add(new Option(c+' · '+count,c));});collection.value=previous;
    // Always default to a scene — never show all 2774 assets at once
    if(!collection.value){const preferred=['Barco · personajes','Agua · personajes','Entrega · dependencias del barco','Interfaz'];collection.value=preferred.find(c=>categories.includes(c))||categories[0]||'';};
    const focused=!previousView&&focusId&&state.frames.find(f=>f.id===focusId);
    if(focused)collection.value=focused.category;
    resize();rebuild();
    if(focused&&!items.some(f=>f.id===focusId)){
      search.value='';filter.value='all';panel.querySelector('[data-edge-filter]').value='all';panel.querySelector('[data-problem]').value='';panel.querySelector('[data-similarity]').value='100';rebuild();
    }
    if(previousView)restoreView(previousView);else fit();
    if(focused)selected=items.findIndex(f=>f.id===focusId);
    if(focused&&selected>=0){
      panX=width/2-((selected%cols)*CW+(CW-14)/2)*scale;
      panY=height/2-(Math.floor(selected/cols)*CH+(CH-14)/2)*scale;
      canvas.focus({preventScroll:true});
    }
    viewReady=true;rememberView();invalidate();
  }
  function hide(){rememberView();if(panel)panel.hidden=true;active=false;}
  return {open,hide};
})();
async function openAssetBrowser(){try{await save();await assetGrid.open({focusId:state.info?.frame.id});}catch(error){message(error.message,true);}}
const assetBrowserButton=document.createElement('button');assetBrowserButton.textContent='Explorar assets';assetBrowserButton.className='accent';document.querySelector('header').insertBefore(assetBrowserButton,confiteButton);assetBrowserButton.onclick=openAssetBrowser;
async function startAssetApp(){
  const route=initialAssetRoute(),assetId=route.asset;
  try{
    if(!assetId){await assetGrid.open();return;}
    const info=await api('/api/open?id='+encodeURIComponent(assetId));
    await openAssetReview(info.frame,route.version,info);
  }catch(error){imageLabNotice(error.message);}
}
if(document.readyState==='complete')startAssetApp();else window.addEventListener('load',startAssetApp,{once:true});



