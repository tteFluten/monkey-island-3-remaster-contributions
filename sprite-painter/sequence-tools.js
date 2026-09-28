'use strict';
// A sequence is the existing costume/resource group, not an inferred animation script.
const SequenceTools = {
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
    bria:{label:'Crear alpha',icon:'scan-line',engine:'Bria · Replicate',paid:true},
    imagelab:{label:'Crear alpha',icon:'wand-sparkles',engine:'ImageLab',paid:true},
    clean:{label:'Limpiar borde',icon:'scissors',engine:'Local'},
    tint:{label:'Oscurecer halo',icon:'paintbrush',engine:'Local'},
    magenta:{label:'Quitar magenta',icon:'pipette',engine:'Local'},
    'white-2':{label:'Borde blanco · 2 px',icon:'circle',engine:'Local'},
    'red-4':{label:'Borde rojo · 4 px',icon:'circle',engine:'Local'}
  },
  payload(frame,recipe){
    const {technique}=recipe;
    if(!this.recipes[technique])throw new Error('Técnica desconocida.');
    if(technique==='upscale')return {url:'/api/upscale/jobs',body:{id:frame.id,enhance_model:recipe.model}};
    if(technique==='generate')return {url:'/api/imagelab/jobs',body:{id:frame.id,model:recipe.model,prompt:recipe.prompt,
      alpha_mode:recipe.alpha||'none',preserve_alpha:recipe.alpha==='ai',style_id:'',
      ...(recipe.base==='current'?{base_kind:'current',base_revision:frame.revision}:{base_kind:'original'})}};
    if(['bria','imagelab'].includes(technique))return {url:'/api/variants/extract-alpha',body:{id:frame.id,revision:frame.revision,engine:technique,...(technique==='imagelab'?{model:recipe.model}:{})}};
    const edge=['clean','tint'].includes(technique);
    return {url:'/api/variants/refine-alpha',body:{id:frame.id,revision:frame.revision,
      trim_pixels:technique==='clean'?recipe.trim:0,tint_strength:edge?recipe.tint:0,
      protect_dark:edge,protect_seams:edge&&recipe.seams,remove_magenta:technique==='magenta',
      ...(technique==='white-2'||technique==='red-4'?{outline:technique}:{})}};
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
      <p class="sq-source" data-source></p><label class="sq-check"><input data-skip type="checkbox"> Omitir cuadros aprobados</label>
      <p data-eligibility></p></div><details data-errors hidden><summary>Errores de envío</summary><pre></pre></details></div>
      <footer><p data-progress role="status"></p><button class="accent" data-send>Encolar cuadros</button></footer>`;
    const q=name=>dialog.querySelector('[data-'+name+']');q('total').textContent=ids.size;
    q('prompt').value=typeof imageLabDefaultPrompt==='string'?imageLabDefaultPrompt:'';
    let technique=initial||'upscale',sending=false,aiInfo=null,aiLoading=false,modelChoices={upscale:'Wonder 3.5 High + Bria'};
    const sections={generation:['upscale','generate'],alpha:['bria','imagelab'],local:['clean','tint','magenta','white-2','red-4']};
    const family=()=>Object.keys(sections).find(k=>sections[k].includes(technique));
    const currentFrames=()=>state.frames.filter(f=>ids.has(f.id));
    const recipe=()=>({technique,model:q('model').value,prompt:q('prompt').value,base:q('base').value,alpha:q('alpha').value,
      trim:Number(q('trim').value),tint:Number(q('tint').value)/100,seams:q('seams').checked,skipApproved:q('skip').checked});
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
      q('ai').hidden=technique!=='generate';q('edge').hidden=!['clean','tint'].includes(technique);q('trim-label').hidden=technique!=='clean';
      const source=technique==='upscale'?'Base: original de cada cuadro.':technique==='generate'?`Base: ${q('base').value==='current'?'versión en uso':'original'} de cada cuadro. Referencia fija: su propio original, para pose, paleta y trazo.`:'Base: versión en uso de cada cuadro.';
      q('source').textContent=source+' '+(this.recipes[technique].paid?'Consume créditos del motor elegido.':'Local · sin créditos.');
      q('progress').textContent='';refresh();if(needsAI()&&!aiInfo)loadAI();
    };
    for(const button of dialog.querySelectorAll('[data-tab]'))button.onclick=()=>{technique=sections[button.dataset.tab][0];render();};
    q('model').onchange=()=>{modelChoices[technique]=q('model').value;refresh();};
    q('base').onchange=render;for(const name of ['alpha','trim','tint','seams','skip'])q(name).onchange=refresh;
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
