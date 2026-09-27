'use strict';
// Keep the asset catalogue, revision checks and history in the workshop; paint in Confite.
let confiteSession = null;
const workshopStyle=document.createElement('link');workshopStyle.rel='stylesheet';workshopStyle.href='/confite-workshop.css';document.head.append(workshopStyle);
const workshopTheme=document.createElement('link');workshopTheme.rel='stylesheet';workshopTheme.href='/workshop-theme.css';document.head.append(workshopTheme);
let onionSettings={enabled:true,previous:true,next:true,opacity:.25,alignment:'feet',previousColor:'#ff729e',nextColor:'#60d8f5'};
try{Object.assign(onionSettings,JSON.parse(localStorage.getItem('monkey-confite-onion')||'{}'));}catch{}
function syncOnion(){sendConfite('CONFITE_SPRITE_ONION',{settings:onionSettings});try{localStorage.setItem('monkey-confite-onion',JSON.stringify(onionSettings));}catch{}}
const confiteButton = document.createElement('button');
confiteButton.textContent = 'Retocar en Confite';
confiteButton.className = 'accent';
document.querySelector('header').insertBefore(confiteButton, $('export'));
function sendConfite(type, extra = {}) {
  if (confiteSession) confiteSession.frame.contentWindow.postMessage({type, session: confiteSession.token, ...extra}, location.origin);
}
async function confiteDocument() {
  const neighbors = [], directions=[];
  for (const index of [state.index - 1, state.index + 1]) {
    const neighbor = state.sequence[index];
    if (!neighbor) continue;
    try {
      const item = await resource(neighbor), canvas = document.createElement('canvas');
      canvas.width = item.image.width; canvas.height = item.image.height;
      canvas.getContext('2d').drawImage(item.image, 0, 0);
      neighbors.push(canvas.toDataURL('image/png'));
      directions.push(index-state.index);
    } catch { /* Allow editing when a neighboring LFS file is missing. */ }
  }
  let original,originalName;
  const current=state.sequence[state.index];
  if(current.has_reference){
    const response=await fetch('/api/reference?id='+current.id);
    if(!response.ok)throw new Error('No se pudo cargar la capa Original. Comprobá su descarga desde LFS.');
    const blob=await response.blob();
    original=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
    originalName=current.reference_kind==='original-preparado'?'Original · alfa limpio':'Original del juego';
  }
  return {png:pixels.toDataURL('image/png'), width:pixels.width, height:pixels.height, name:state.info.frame.name, neighbors,directions,original,originalName};
}
function confiteNavigate(index) {
  const s=confiteSession;
  if(!s?.ready || s.saving || s.transition || index===state.index || index<0 || index>=state.sequence.length)return;
  s.nextIndex=index;s.transition=true;s.frame.style.pointerEvents='none';
  sendConfite('CONFITE_SPRITE_EXPORT');
}
function confiteFooter(s) {
  const footer=document.createElement('div');
  footer.className='cf-timeline';
  const strip=document.createElement('div');strip.style.minWidth='0';
  const transport=document.createElement('div');transport.className='cf-transport';
  transport.innerHTML='<button data-prev title="Anterior · Alt + ←">←</button><strong class="cf-counter" data-counter></strong><button data-next title="Siguiente · Alt + →">→</button><button data-preview>▶ Preview</button><div data-ranges></div><span class="cf-spacer"></span><button data-problem title="Prioriza rechazos registrados y luego pendientes de validación">Ir a problema</button><details class="cf-onion"><summary>Onion skin ⚙</summary><div class="cf-onion-panel"><strong>Comparar cuadros vecinos</strong><label><input type="checkbox" data-setting="enabled"> Activar onion skin</label><label><input type="checkbox" data-setting="previous"> Anterior<input type="color" aria-label="Color anterior" data-setting="previousColor"></label><label><input type="checkbox" data-setting="next"> Siguiente<input type="color" aria-label="Color siguiente" data-setting="nextColor"></label><label>Opacidad<input aria-label="Opacidad onion skin" type="range" min="0" max="80" data-setting="opacity"><output data-opacity></output></label><label>Alinear<select aria-label="Alineación onion skin" data-setting="alignment"><option value="feet">Centro / pies</option><option value="center">Centro</option><option value="origin">Origen</option></select></label><small>Referencias visuales; no se exportan al PNG.</small></div></details>';
  const side=document.createElement('div');
  const controls=document.querySelector('.preview-controls');
  s.moved=[$('timeline'),$('preview'),controls].map(node=>{
    const marker=document.createComment('Confite timeline');node.before(marker);
    return {node,marker,style:node.getAttribute('style')};
  });
  $('timeline').removeAttribute('style');$('preview').removeAttribute('style');controls.removeAttribute('style');
  transport.querySelector('[data-ranges]').append(controls);
  strip.append($('timeline'));side.append($('preview'));
  const review=document.createElement('div');review.className='cf-review-line';review.innerHTML='<span data-quality></span> <span class="cf-muted">· rojo: rechazo · ámbar: revisar · sin marca: sin alerta registrada</span>';strip.append(review);
  const body=document.createElement('div');body.className='cf-body';body.append(strip,side);footer.append(transport,body);s.overlay.append(footer);
  s.footer=footer;
  for(const input of footer.querySelectorAll('[data-setting]')){
    const key=input.dataset.setting;
    if(input.type==='checkbox')input.checked=onionSettings[key];else input.value=key==='opacity'?onionSettings[key]*100:onionSettings[key];
    input.oninput=()=>{onionSettings[key]=input.type==='checkbox'?input.checked:key==='opacity'?+input.value/100:input.value;footer.querySelector('[data-opacity]').textContent=Math.round(onionSettings.opacity*100)+'%';syncOnion();};
  }
  footer.querySelector('[data-opacity]').textContent=Math.round(onionSettings.opacity*100)+'%';
  footer.querySelector('[data-problem]').onclick=()=>{
    const issues=state.sequence.map((frame,index)=>({index,priority:reviewInfo(frame).priority})).filter(x=>x.priority>0).sort((a,b)=>b.priority-a.priority||a.index-b.index);
    const current=issues.findIndex(x=>x.index===state.index);const target=issues[(current+1)%issues.length];if(target)confiteNavigate(target.index);
  };
  s.timelineClick=event=>{const button=event.target.closest('button[data-index]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();confiteNavigate(+button.dataset.index);};
  $('timeline').addEventListener('click',s.timelineClick,true);
  footer.querySelector('[data-prev]').onclick=()=>confiteNavigate(state.index-1);
  footer.querySelector('[data-next]').onclick=()=>confiteNavigate(state.index+1);
  footer.querySelector('[data-preview]').onclick=()=>{
    if(state.playing){state.playing=false;footer.querySelector('[data-preview]').textContent='▶ Preview';return;}
    if(!s.ready||s.saving||s.transition)return;
    s.previewRequested=true;sendConfite('CONFITE_SPRITE_EXPORT');
  };
  confiteCounter(s);
}
function confiteCounter(s){
  s.footer.querySelector('[data-counter]').textContent=`${state.index+1} / ${state.sequence.length}`;
  s.footer.querySelector('[data-prev]').disabled=state.index===0;
  s.footer.querySelector('[data-next]').disabled=state.index===state.sequence.length-1;
  let count=0;
  for(const button of $('timeline').children){const info=reviewInfo(state.sequence[+button.dataset.index]);button.dataset.review=info.priority===2?'bad':info.priority===1?'check':'';button.title=state.sequence[+button.dataset.index].name+' — '+info.text;if(info.priority)count++;}
  const current=reviewInfo(state.sequence[state.index]);s.footer.querySelector('[data-quality]').textContent=current.text;
  s.footer.querySelector('[data-problem]').disabled=!count;s.footer.querySelector('[data-problem]').textContent=count?'Ir a problema · '+count:'Sin alertas registradas';
}
function reviewInfo(frame){
  const r=frame?.review;if(!r)return {priority:0,text:'Sin evaluación registrada'};
  const suffix=frame.edited?' · master evaluado; retoque pendiente de evaluar':'';
  if(!r.current)return {priority:0,text:'Revisión de otra versión; no aplicable al master actual'};
  const priority=r.state==='rejected'?2:r.validation_passed===false||r.state?.startsWith('draft-')?1:0;
  const labels={rejected:'Rechazado en revisión',validated:'Validación técnica pasada',accepted:'Aceptado', 'draft-redraw':'Redibujo por revisar','draft-derived':'Derivado por revisar','manual-edit':'Edición manual'};
  let text=(labels[r.state]||r.state)+suffix;
  const iou=r.validation?.silhouette_iou;if(Number.isFinite(iou))text+=' · coincidencia de silueta '+Math.round(iou*100)+'%';
  if(r.note)text+=' · '+r.note;
  return {priority,text};
}
function closeConfite(s){
  $('timeline').removeEventListener('click',s.timelineClick,true);
  for(const {node,marker,style} of s.moved){marker.replaceWith(node);if(style===null)node.removeAttribute('style');else node.setAttribute('style',style);}
  s.overlay.remove();confiteSession=null;state.busy=false;state.playing=false;$('play').textContent='▶ Reproducir';status();invalidate();
  if(!s.goBrowser)s.onReviewReturn?.();
}
async function showConfiteHistory(s){
  const id=state.info.frame.id;
  const dialog=document.createElement('dialog');dialog.className='imagelab-dialog';
  dialog.innerHTML='<div class="il-heading"><strong>Historial de guardados</strong><button data-dismiss>Cerrar</button></div><p>Restaurar conserva también la versión actual. Son versiones PNG; las capas editables se conservan con Save project (.confite).</p><select aria-label="Versión guardada" data-versions></select><div class="il-images"><figure><figcaption>Actual</figcaption><img data-now></figure><figure><figcaption>Versión anterior</figcaption><img data-before></figure></div><p data-message role="status"></p><button data-restore disabled>Restaurar y seguir editando</button>';
  const q=k=>dialog.querySelector('[data-'+k+']');
  q('now').src=pixels.toDataURL('image/png');
  q('dismiss').onclick=()=>{dialog.close();dialog.remove();};
  document.body.append(dialog);dialog.showModal();
  try{
    const {items}=await api('/api/history?id='+id);
    for(const name of items)q('versions').add(new Option(new Date(Number(name.split('-')[0])/1e6).toLocaleString(),name));
    q('versions').onchange=()=>{q('before').src='/api/version?id='+id+'&name='+q('versions').value;};
    if(items.length){q('versions').onchange();q('restore').disabled=false;}else q('message').textContent='Todavía no hay guardados anteriores.';
    q('restore').onclick=async()=>{
      q('restore').disabled=true;
      try{
        const result=await api('/api/restore',{id,name:q('versions').value,revision:state.info.revision});
        cache.delete(id);state.busy=false;await navigate(state.index);state.busy=true;
        if(state.info.revision!==result.revision)throw new Error('La versión se restauró. Cerrá y reabrí el editor para cargarla.');
        s.document=await confiteDocument();s.lastExport=null;s.ready=false;s.transition=true;
        sendConfite('CONFITE_SPRITE_OPEN',{document:s.document});
        dialog.close();dialog.remove();
      }catch(error){q('message').textContent=error.message;q('restore').disabled=false;}
    };
  }catch(error){q('message').textContent=error.message;}
}
confiteButton.onclick = async (options = {}) => {
  if (!state.info || state.busy || state.pointer || confiteSession) return;
  state.busy = true; state.playing = false; $('play').textContent = '▶ Reproducir'; status();
  try {
    await save();
    const documentData=await confiteDocument();
    if(options.hiddenLayers)documentData.hiddenLayers=options.hiddenLayers;
    const overlay = document.createElement('section');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:10000;background:#111;display:flex;flex-direction:column';
    overlay.innerHTML = '<div style="min-height:48px;display:flex;gap:12px;align-items:center;padding:8px 16px;flex-wrap:wrap"><button data-browser>← Assets</button><strong>MONKEY × CONFITE</strong><span data-status role="status" style="flex:1">Abriendo sprite…</span><button data-reference-toggle aria-pressed="true">Original</button><button data-save>Guardar borrador · Ctrl S</button><button data-close>Guardar y volver a preview</button></div>';
    const frame = document.createElement('iframe');
    frame.title = 'Confite — retoque del sprite';
    frame.style.cssText = 'border:0;flex:1;width:0;min-width:0;height:100%';
    const session = {token: crypto.randomUUID(), overlay, frame, ready:false, sent:false, saving:false, closing:false,
      document:documentData};
    confiteSession = session;
    const historyButton=document.createElement('button');historyButton.textContent='Historial';
    historyButton.onclick=()=>{if(!session.ready||session.saving||session.transition)return;session.historyRequested=true;sendConfite('CONFITE_SPRITE_EXPORT');};
    overlay.querySelector('[data-save]').before(historyButton);
    overlay.querySelector('[data-save]').disabled = true;
    overlay.querySelector('[data-close]').disabled = true;
    overlay.querySelector('[data-save]').onclick = () => sendConfite('CONFITE_SPRITE_EXPORT');
    overlay.querySelector('[data-close]').onclick = () => { if(session.saving||session.transition)return; session.closing=true; sendConfite('CONFITE_SPRITE_EXPORT'); };
    overlay.querySelector('[data-browser]').onclick=()=>{if(!session.ready||session.saving||session.transition)return;session.goBrowser=true;session.closing=true;sendConfite('CONFITE_SPRITE_EXPORT');};
    frame.src = '/confite/?spriteBridge=1';
    const editorRow=document.createElement('div');editorRow.className='cf-editor-row';
    editorRow.append(frame);overlay.append(editorRow);document.body.append(overlay);
    overlay.querySelector('[data-reference-toggle]').remove();
    confiteFooter(session);
    session.timer = setTimeout(() => {
      if (!session.ready && confiteSession === session) {
        overlay.querySelector('[data-status]').textContent='Confite no terminó de abrir. Cerrá y volvé a intentar.';
        const close = overlay.querySelector('[data-close]'); close.disabled=false; close.textContent='Volver';
        close.onclick=()=>closeConfite(session);
      }
    }, 30000);
  } catch (error) { state.busy=false;status();message(error.message,true); }
};
window.addEventListener('message', async event => {
  const s = confiteSession;
  if (!s || event.source !== s.frame.contentWindow || event.origin !== location.origin) return;
  const data = event.data;
  if (data?.type === 'CONFITE_SPRITE_READY' && !s.sent) {
    s.sent=true; sendConfite('CONFITE_SPRITE_OPEN', {document:s.document}); return;
  }
  if (!data || data.session !== s.token) return;
  const label = s.overlay.querySelector('[data-status]');
  if (data.type === 'CONFITE_SPRITE_LOADED') {
    s.transition=false;s.frame.style.pointerEvents='';confiteCounter(s);
    syncOnion();
    s.ready=true;clearTimeout(s.timer);label.textContent=state.info.frame.name+' · los originales se conservan';
    s.overlay.querySelector('[data-save]').disabled=false;s.overlay.querySelector('[data-close]').disabled=false;
  } else if (data.type === 'CONFITE_SPRITE_NAVIGATE') {
    if(data.delta===-1||data.delta===1)confiteNavigate(state.index+data.delta);
  } else if (data.type === 'CONFITE_SPRITE_ERROR') {
    label.textContent=data.error; s.closing=false;s.transition=false;s.nextIndex=null;s.frame.style.pointerEvents='';
  } else if (data.type === 'CONFITE_SPRITE_PNG' && s.ready && !s.saving) {
    s.saving=true;label.textContent='Guardando borrador…';
    try {
      if(typeof data.png !== 'string' || !data.png.startsWith('data:image/png;base64,')) throw new Error('PNG inválido.');
      const image=await loadImage(data.png);
      if(image.width !== pixels.width || image.height !== pixels.height) throw new Error('El lienzo cambió de tamaño. Volvé a las dimensiones originales antes de guardar.');
      if(data.png !== s.lastExport && data.png !== pixels.toDataURL('image/png')) {
        checkpoint();paint.clearRect(0,0,pixels.width,pixels.height);paint.drawImage(image,0,0);changed();
        state.sequence[state.index].edited=true;
      }
      await save();s.lastExport=data.png;confiteCounter(s);label.textContent='✓ PNG guardado. Para conservar capas: Save project (.confite).';
      if(s.historyRequested){s.historyRequested=false;await showConfiteHistory(s);}
      else if(s.closing){closeConfite(s);if(s.goBrowser)await openAssetBrowser();}
      else if(s.nextIndex!=null){
        const index=s.nextIndex;s.nextIndex=null;state.playing=false;s.footer.querySelector('[data-preview]').textContent='▶ Preview';
        // Decode before switching the host document so a missing asset keeps the current frame safe.
        await resource(state.sequence[index]);
        state.busy=false;await navigate(index);state.busy=true;
        if(state.index!==index)throw new Error('No se pudo abrir el cuadro. El anterior quedó guardado.');
        s.document=await confiteDocument();s.lastExport=null;
        sendConfite('CONFITE_SPRITE_OPEN',{document:s.document});
        label.textContent='Abriendo cuadro '+(index+1)+'…';
      }else if(s.previewRequested){
        s.previewRequested=false;state.playing=true;state.playIndex=previewRange()[0];state.playTime=performance.now();
        s.footer.querySelector('[data-preview]').textContent='Ⅱ Pausar';
      }
    } catch(error){label.textContent=error.message;s.closing=false;s.transition=false;s.nextIndex=null;s.previewRequested=false;s.frame.style.pointerEvents='';}
    finally{s.saving=false;}
  }
});
window.addEventListener('beforeunload', event=>{if(confiteSession){event.preventDefault();event.returnValue='';}});
window.addEventListener('keydown',event=>{
  if(confiteSession && event.altKey && ['ArrowLeft','ArrowRight'].includes(event.key)){
    event.preventDefault();event.stopImmediatePropagation();confiteNavigate(state.index+(event.key==='ArrowLeft'?-1:1));
  }
},true);
