'use strict';
// Track the exact submitted jobs, not whichever older result happens to exist.
function createSpriteBatchTracker(storage){
  const key='monkey-generation-batches-v1',listeners=new Set();let batches=[];
  try{batches=JSON.parse(storage?.getItem(key)||'[]').filter(b=>b.id&&Array.isArray(b.entries)).slice(0,8);}catch{}
  for(const batch of batches)for(const e of batch.entries)if(['pending','sending'].includes(e.status)){e.status='unsent';e.error='El envío no se confirmó antes de cerrar. Revisá la cola antes de volver a generar.';}
  function changed(){try{storage?.setItem(key,JSON.stringify(batches));}catch{}for(const fn of listeners)fn();}
  const summarize=j=>Object.fromEntries(['id','asset_id','status','image','error','stage','candidate_sha256','base_revision','created_at','quality'].map(k=>[k,j[k]]));
  function state(e){if(e.approved)return 'approved';if(e.job?.status==='applied')return 'applied';if(['failed','cancelled','interrupted'].includes(e.job?.status)||e.status==='error')return 'error';if(['ready','applied'].includes(e.job?.status)&&e.job?.image)return 'ready';if(e.job?.status==='running')return 'running';if(e.job?.status==='queued')return 'queued';return 'pending';}
  return {
    all:()=>batches, get:id=>batches.find(b=>b.id===id),state,
    subscribe(fn){listeners.add(fn);return ()=>listeners.delete(fn);},
    begin(requests,label){const batch={id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8),label,created:Date.now(),entries:requests.map(r=>({asset_id:r.body.id,name:r.name,status:'pending'}))};batches.unshift(batch);batches=batches.slice(0,8);changed();return batch;},
    update(id,asset,patch){const e=batches.find(b=>b.id===id)?.entries.find(e=>e.asset_id===asset);if(!e)return;Object.assign(e,patch);if(patch.job)e.job=summarize(patch.job);changed();},
    finish(id){const b=this.get(id);if(!b)return;for(const e of b.entries)if(e.status==='pending'){e.status='unsent';e.error='No enviado · se detuvo la tanda.';}changed();},
    ingest(jobs,approvals){const index=new Map(jobs.map(j=>[j.id,j]));let dirty=false;for(const b of batches)for(const e of b.entries){const before=JSON.stringify(e);const job=index.get(e.job?.id);if(job&&job.asset_id===e.asset_id)e.job=summarize(job);if(approvals)e.approved=!!(e.job?.candidate_sha256&&approvals[e.asset_id]?.sha256===e.job.candidate_sha256);if(JSON.stringify(e)!==before)dirty=true;}if(dirty)changed();},
    counts(batch){const result={all:batch.entries.length,pending:0,queued:0,running:0,ready:0,applied:0,approved:0,error:0};for(const e of batch.entries)result[state(e)]++;return result;},
    entry(id,asset){return this.get(id)?.entries.find(e=>e.asset_id===asset);}
  };
}
const SpriteBatches=createSpriteBatchTracker(typeof localStorage==='undefined'?null:localStorage);
// A sequence is the existing costume/resource group, not an inferred animation script.
const SequenceTools = {
  createBatchTracker:createSpriteBatchTracker,
  waterFrames(frames){return frames.filter(f=>/^LFLF_0011_.*_frame_\d+$/i.test(f.name));},
  results(frames,jobs,includeWarnings=false){
    const newest=new Map();
    for(const job of [...jobs].sort((a,b)=>b.created_at-a.created_at))if(!newest.has(job.asset_id))newest.set(job.asset_id,job);
    return frames.map(frame=>{
      const job=newest.get(frame.id);
      const reason=!job?'Sin generación':job.status==='applied'?'Ya aplicado':job.status!=='ready'?(['queued','running'].includes(job.status)?'En proceso':'Falló'):!job.image?'Sin imagen':job.base_revision===undefined?'Sin revisión de origen':frame.revision!=null&&job.base_revision!==frame.revision?'Cambió la versión en uso':job.quality?.passed===false&&!includeWarnings?'Con alertas · revisar':'';
      return {frame,job,reason};
    });
  },
  async refreshAssets(ids){
    for(let i=0;i<ids.length;i+=60)LiveAssets.merge(await api('/api/live-state?ids='+ids.slice(i,i+60).join(',')));
  },
  async reviewResults(frames,exactJobs=null){
    const ids=new Set(frames.map(f=>f.id)),dialog=document.createElement('dialog');dialog.className='sq-batch-dialog';
    dialog.setAttribute('aria-label','Aplicar resultados de la selección');
    dialog.innerHTML='<header><h2>Resultados de la selección</h2><button data-close>Cerrar</button></header><div class="sq-batch-body"><p>Última generación de cada cuadro. Aplicar la pone en uso y conserva el historial. Los cuadros editados después de generar se omiten.</p><label><input type="checkbox" data-warnings> Incluir resultados con alertas visuales</label><label><input type="checkbox" data-approve> Aprobar también los resultados aplicados</label><p data-summary role="status"></p><div data-results style="max-height:45vh;overflow:auto"></div><p data-progress role="status"></p></div><footer><button data-refresh>Actualizar</button><button data-apply class="accent" disabled>Aplicar resultados</button></footer>';
    const q=k=>dialog.querySelector('[data-'+k+']');let rows=[],busy=false,timer;
    if(exactJobs)dialog.querySelector('.sq-batch-body>p').textContent='Resultados de esta tanda, aunque existan otras generaciones más nuevas. Aplicar conserva el historial; los cuadros editados después de generar se omiten.';
    const render=()=>{
      const eligible=rows.filter(r=>!r.reason);q('summary').textContent=`${eligible.length} listos para aplicar · ${rows.length-eligible.length} omitidos · ${rows.length} seleccionados`;
      q('apply').disabled=busy||!eligible.length;q('apply').textContent=`Aplicar ${eligible.length} resultados`;
      q('results').replaceChildren(...rows.map(({frame,job,reason})=>{
        const row=document.createElement('div');row.style.cssText='display:flex;align-items:center;gap:12px;padding:8px;border-bottom:1px solid #333';
        if(job?.image){const img=document.createElement('img');img.src=job.image;img.alt='';img.style.cssText='width:64px;height:56px;object-fit:contain';row.append(img);}
        const label=document.createElement('span');label.textContent=frame.name+' · '+(reason||'Listo para aplicar');row.append(label);return row;
      }));
    };
    const refresh=async()=>{
      clearTimeout(timer);if(busy||!dialog.isConnected)return;
      try{await this.refreshAssets([...ids]);const result=await api('/api/imagelab/jobs?ids='+[...ids].join(','));if(!dialog.isConnected)return;
        rows=this.results(state.frames.filter(f=>ids.has(f.id)),exactJobs?result.jobs.filter(j=>exactJobs.get(j.asset_id)===j.id):result.jobs,q('warnings').checked);render();
      }catch(error){q('progress').textContent=error.message;}
      if(dialog.isConnected)timer=setTimeout(refresh,3000);
    };
    q('close').onclick=()=>{if(busy)return;clearTimeout(timer);dialog.close();dialog.remove();};
    dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();else{clearTimeout(timer);dialog.remove();}});
    q('refresh').onclick=refresh;q('warnings').onchange=refresh;
    q('apply').onclick=async()=>{
      if(busy)return;busy=true;clearTimeout(timer);
      const targets=rows.filter(r=>!r.reason).map(r=>({id:r.frame.id,name:r.frame.name,revision:r.frame.revision??r.job.base_revision,job:r.job.id})),approve=q('approve').checked;
      for(const el of dialog.querySelectorAll('button,input'))el.disabled=true;
      let applied=0,approved=0;const errors=[];
      try{for(const target of targets){
        q('progress').textContent=`Aplicando ${applied+errors.length+1}/${targets.length}…`;
        try{const saved=await api('/api/variants/select',{job_id:target.job,revision:target.revision});applied++;
          if(approve){await api('/api/imagelab/approve',{id:target.id,revision:saved.revision});approved++;}
        }catch(error){errors.push(target.name+': '+error.message);}
        try{await this.refreshAssets([target.id]);}catch{LiveAssets.request([target.id]);}
      }}finally{
        busy=false;for(const el of dialog.querySelectorAll('button,input'))el.disabled=false;
        q('progress').textContent=`${applied} aplicados${approve?' · '+approved+' aprobados':''} · ${errors.length} errores. ${errors.join(' · ')}`;
        await refresh();
      }
    };
    document.body.append(dialog);dialog.showModal();await refresh();
  },
  key(frame){return JSON.stringify([frame.category||'',frame.group||frame.id]);},
  groups(all,filtered){
    const matches=new Set(filtered.map(f=>f.id)),groups=new Map();
    for(const frame of all){
      const key=this.key(frame);
      if(!groups.has(key))groups.set(key,{id:'sequence:'+key,key,category:frame.category,frames:[],matching:0});
      const group=groups.get(key);group.frames.push(frame);if(matches.has(frame.id))group.matching++;
    }
    const rank=new Map(filtered.map((f,i)=>[f.id,i]));
    return [...groups.values()].filter(g=>g.matching).map(g=>{
      g.frames.sort((a,b)=>(a.number??0)-(b.number??0)||a.name.localeCompare(b.name,undefined,{numeric:true}));
      g.name=(g.frames[0].group||g.frames[0].name).split('/').pop().replace(/_a?frame$/,'');
      g.rank=Math.min(...g.frames.map(f=>rank.get(f.id)??Infinity));return g;
    }).sort((a,b)=>a.rank-b.rank);
  },
  recipes:{
    upscale:{label:'Escalar original',icon:'scan-line',engine:'Topaz / Replicate',paid:true},
    generate:{label:'Generar con prompt',icon:'wand-sparkles',engine:'ImageLab',paid:true},
    alphaoriginal:{label:'Alpha del original',icon:'scan-line',engine:'Local'},
    bria:{label:'Crear alpha',icon:'scan-line',engine:'Bria · Replicate',paid:true},
    imagelab:{label:'Crear alpha',icon:'wand-sparkles',engine:'ImageLab',paid:true},
    clean:{label:'Limpiar borde',icon:'scissors',engine:'Local'},
    tint:{label:'Oscurecer halo',icon:'paintbrush',engine:'Local'},
    magenta:{label:'Quitar magenta',icon:'pipette',engine:'Local'},
    outline:{label:'Agregar contorno',icon:'circle',engine:'Local'}
  },
  payload(frame,recipe){
    const {technique}=recipe;
    if(!this.recipes[technique])throw new Error('Técnica desconocida.');
    if(technique==='upscale')return {url:'/api/upscale/jobs',body:{id:frame.id,enhance_model:recipe.model}};
    if(technique==='generate')return {url:'/api/imagelab/jobs',body:{id:frame.id,model:recipe.model,prompt:recipe.prompt,
      alpha_mode:recipe.alpha||'none',preserve_alpha:recipe.alpha==='ai',style_id:'',
      ...(recipe.base==='current'?{base_kind:'current',base_revision:frame.revision}:{base_kind:'original'})}};
    if(technique==='alphaoriginal')return {url:'/api/variants/refine-alpha',body:{id:frame.id,revision:frame.revision,alpha_original:true}};
    if(['bria','imagelab'].includes(technique))return {url:'/api/variants/extract-alpha',body:{id:frame.id,revision:frame.revision,engine:technique,...(technique==='imagelab'?{model:recipe.model}:{})}};
    const edge=['clean','tint'].includes(technique);
    return {url:'/api/variants/refine-alpha',body:{id:frame.id,revision:frame.revision,
      trim_pixels:technique==='clean'?recipe.trim:0,tint_strength:edge?recipe.tint:0,
      protect_dark:edge,protect_seams:edge&&recipe.seams,remove_magenta:technique==='magenta',
      ...(technique==='outline'?{outline:'custom',outline_color:recipe.outlineColor||'ffffff',outline_radius:recipe.outlineRadius||2}:{})}};
  },
  plan(frames,recipe,approvals,jobs){
    const requests=[],skipped={busy:0,approved:0,original:0};
    for(const f of new Map(frames.map(f=>[f.id,f])).values()){
      if(['queued','running'].includes(jobs.get(f.id)?.status)){skipped.busy++;continue;}
      if(recipe.skipApproved&&approvals[f.id]){skipped.approved++;continue;}
      if(!f.has_reference&&(['upscale','generate'].includes(recipe.technique)||['clean','tint'].includes(recipe.technique)&&recipe.seams)){skipped.original++;continue;}
      requests.push({name:f.name,...this.payload(f,recipe)});
    }
    return {requests,skipped};
  },
  open(frames,initial,run){
    const ids=new Set(frames.map(f=>f.id)),dialog=document.createElement('dialog');dialog.className='sq-batch-dialog';
    dialog.setAttribute('aria-label','Acciones sobre la selección');
    dialog.innerHTML=`<header><div><small>LOTE · <span data-total></span> CUADROS</small><h2>Procesar selección</h2></div><button data-close>Cerrar</button></header>
      <div class="sq-batch-body"><nav aria-label="Tipo de acción"><button data-tab="generation">Generación</button><button data-tab="alpha">Alpha</button><button data-tab="local">Bordes</button></nav>
      <div class="sq-techniques"></div><div class="sq-settings">
      <label data-model-label>Motor y modelo<select data-model aria-label="Modelo del lote"></select></label>
      <div data-ai hidden><label>Imagen que se modifica<select data-base><option value="original">Original de cada cuadro</option><option value="current">Versión en uso de cada cuadro</option></select></label>
      <label>Instrucción para todos los cuadros<textarea data-prompt rows="4"></textarea></label>
      <label>Transparencia<select data-alpha><option value="none">Alpha después · conservar fondo</option><option value="ai">Extraer alpha con ImageLab</option></select></label></div>
      <div data-edge hidden><label data-trim-label>Recortar (px)<input data-trim type="number" min="0" max="3" step="0.25" value="0.5"></label><label>Oscurecer halo (%)<input data-tint type="number" min="0" max="100" value="70"></label><label class="sq-check"><input data-seams type="checkbox" checked> Proteger empalmes rectos del original</label></div>
      <div data-outline-opts hidden><label>Color del contorno<select data-ol-color><option value="ffffff">Blanco</option><option value="ff3b0f">Rojo</option><option value="000000">Negro</option></select></label><label>Radio (px)<input data-ol-radius type="number" min="1" max="8" step="1" value="2"></label></div>
      <p class="sq-source" data-source></p><label class="sq-check"><input data-skip type="checkbox"> Omitir cuadros aprobados</label>
      <p data-eligibility></p></div><details data-errors hidden><summary>Errores de envío</summary><pre></pre></details></div>
      <footer><p data-progress role="status"></p><button class="accent" data-send>Encolar cuadros</button></footer>`;
    const q=name=>dialog.querySelector('[data-'+name+']');q('total').textContent=ids.size;
    q('prompt').value=typeof imageLabDefaultPrompt==='string'?imageLabDefaultPrompt:'';
    let technique=initial||'upscale',sending=false,aiInfo=null,aiLoading=false,modelChoices={upscale:'Wonder 3.5 High + Bria'};
    const sections={generation:['upscale','generate'],alpha:['alphaoriginal','bria','imagelab'],local:['clean','tint','magenta','outline']};
    const family=()=>Object.keys(sections).find(k=>sections[k].includes(technique));
    const currentFrames=()=>state.frames.filter(f=>ids.has(f.id));
    const recipe=()=>({technique,model:q('model').value,prompt:q('prompt').value,base:q('base').value,alpha:q('alpha').value,
      trim:Number(q('trim').value),tint:Number(q('tint').value)/100,seams:q('seams').checked,skipApproved:q('skip').checked,
      outlineColor:q('ol-color').value,outlineRadius:Number(q('ol-radius').value)});
    const plan=()=>this.plan(currentFrames(),recipe(),imageLabApprovals,imageLabAssetJobs);
    const needsAI=()=>['generate','imagelab'].includes(technique);
    function refresh(){
      if(sending)return;
      const {requests,skipped}=plan(),reasons=[];
      if(skipped.busy)reasons.push(`${skipped.busy} ya en proceso`);
      if(skipped.approved)reasons.push(`${skipped.approved} aprobados omitidos`);
      if(skipped.original)reasons.push(`${skipped.original} sin original`);
      q('eligibility').textContent=`${requests.length} de ${ids.size} cuadros${reasons.length?' · '+reasons.join(' · '):''}. Se crean versiones para revisar.`;
      const modelError=needsAI()&&!aiInfo?.ready;
      q('send').disabled=sending||!requests.length||modelError||(['upscale','generate','imagelab'].includes(technique)&&!q('model').value);
      q('send').textContent=`Encolar ${requests.length} cuadros`;
      if(modelError)q('progress').textContent=aiLoading?'Conectando con ImageLab…':aiInfo?.error||'ImageLab no está disponible.';
    }
    async function loadAI(){
      if(aiInfo||aiLoading)return;aiLoading=true;refresh();
      try{aiInfo=await api('/api/imagelab/status');}catch(error){aiInfo={ready:false,error:error.message};}
      finally{aiLoading=false;if(dialog.isConnected&&!sending)render();}
    }
    const render=()=>{
      const group=family();
      for(const button of dialog.querySelectorAll('[data-tab]'))button.setAttribute('aria-pressed',String(button.dataset.tab===group));
      const row=dialog.querySelector('.sq-techniques');row.replaceChildren();
      for(const key of sections[group]){
        const spec=this.recipes[key],button=ReviewUI.button(spec.label+' · '+spec.engine,spec.icon,()=>{technique=key;render();},'ar-tool-card');
        button.dataset.technique=key;button.setAttribute('aria-pressed',String(key===technique));
        const strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=spec.label;small.textContent=spec.engine;button.append(strong,small);row.append(button);
      }
      q('model-label').hidden=!['upscale','generate','imagelab'].includes(technique);
      const models=technique==='upscale'?[['Wonder 3.5 High + Bria','Wonder 3.5 ×4 + Bria'],['Real-ESRGAN Anime 6B','Real-ESRGAN · Anime 6B ×4'],['CGI','Topaz · CGI'],['High Fidelity V2','Topaz · Alta fidelidad'],['Standard V2','Topaz · Estándar']]: (aiInfo?.models||[]).map(m=>[m,m]);
      q('model').replaceChildren(...models.map(([value,label])=>new Option(label,value)));
      const chosen=modelChoices[technique]||aiInfo?.defaultModel;if(models.some(m=>m[0]===chosen))q('model').value=chosen;
      q('ai').hidden=technique!=='generate';q('edge').hidden=!['clean','tint'].includes(technique);q('trim-label').hidden=technique!=='clean';q('outline-opts').hidden=technique!=='outline';
      const source=technique==='upscale'?'Base: original de cada cuadro.':technique==='generate'?`Base: ${q('base').value==='current'?'versión en uso':'original'} de cada cuadro. Referencia fija: su propio original, para pose, paleta y trazo.`:'Base: versión en uso de cada cuadro.';
      q('source').textContent=source+' '+(this.recipes[technique].paid?'Consume créditos del motor elegido.':'Local · sin créditos.');
      q('progress').textContent='';refresh();if(needsAI()&&!aiInfo)loadAI();
    };
    for(const button of dialog.querySelectorAll('[data-tab]'))button.onclick=()=>{technique=sections[button.dataset.tab][0];render();};
    q('model').onchange=()=>{modelChoices[technique]=q('model').value;refresh();};
    q('base').onchange=render;for(const name of ['alpha','trim','tint','seams','skip','ol-color','ol-radius'])q(name).onchange=refresh;
    q('close').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{window.removeEventListener('assets-live',refresh);window.removeEventListener('imagelab-assets',refresh);dialog.remove();});
    q('send').onclick=async()=>{
      if(sending||q('send').disabled)return;
      if(!q('trim').checkValidity()||!q('tint').checkValidity()){q('progress').textContent='Revisá el recorte (0–3 px) y el tinte (0–100%).';return;}
      const {requests}=plan();if(!requests.length)return;sending=true;
      for(const control of dialog.querySelectorAll('input,select,textarea,button:not([data-close])'))control.disabled=true;
      const spec=this.recipes[technique];
      try{
        const result=await run(requests,`${spec.label} · ${spec.engine}`,text=>q('progress').textContent=text);
        if(result.errors.length){q('errors').hidden=false;q('errors').open=true;q('errors').querySelector('pre').textContent=result.errors.join('\n');}
      }catch(error){q('progress').textContent=error.message;}
      // A sent snapshot cannot be submitted twice. Reopen the action for another batch.
      q('send').textContent='Envío finalizado';q('close').textContent='Volver a assets';
    };
    document.body.append(dialog);dialog.showModal();render();
    window.addEventListener('assets-live',refresh);window.addEventListener('imagelab-assets',refresh);
    return dialog;
  }
};
if(typeof module!=='undefined')module.exports=SequenceTools;
