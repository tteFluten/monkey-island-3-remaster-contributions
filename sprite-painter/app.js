'use strict';
const $ = id => document.getElementById(id);
const view = $('view'), ctx = view.getContext('2d');
const pixels = document.createElement('canvas'), paint = pixels.getContext('2d', {willReadFrequently:true});
const preview = $('preview'), pc = preview.getContext('2d');
const state = {frames:[], groups:[], sequence:[], index:0, info:null, base:null, zoom:1, pan:[0,0], tool:'brush',
  undo:[], redo:[], version:0, saved:0, saving:null, busy:false, pointer:null, space:false, cursor:null,
  offset:[0,0], compare:false, playing:false, playIndex:0, playTime:0, dirtyView:true};
const cache = new Map(), pending = new Map();
const tint = document.createElement('canvas'), tc = tint.getContext('2d');
const preferences = ['size','opacity','hardness','pressure','alphaLock','onion','prevGhost','nextGhost','onionOpacity','alignment','matte','fps','color'];
function message(text, error=false){$('message').textContent=text;$('message').title=text;$('message').classList.toggle('error',error);}
function invalidate(){state.dirtyView=true;}
function dirty(){return state.info && state.version!==state.saved;}
function status(){
  $('saveState').textContent=state.saving?'Guardando…':dirty()?'● Retoque sin guardar':state.info?'✓ Guardado / sin cambios':'Abrí una secuencia';
  $('saveState').classList.toggle('dirty',!!dirty());
  $('save').disabled=!dirty()||!!state.saving||state.busy;
  $('export').disabled=!state.info||state.busy;
  $('undo').disabled=!state.undo.length||state.busy;
  $('redo').disabled=!state.redo.length||state.busy;
}
async function api(path, body){
  const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Error de conexión');
  if(body&&!path.startsWith('/api/deliveries')&&path!=='/api/asset-audit'){const id=result.asset_id||body.id||(path==='/api/import'?result.id:null);window.dispatchEvent(new CustomEvent('workspace-write',{detail:{ids:id?[id]:null}}));}
  return result;
}
function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('No se pudo abrir el PNG. Revisá que esté descargado desde LFS.'));image.src=url;});}
function cached(id){return cache.get(id);}
function remember(id,item){cache.delete(id);cache.set(id,item);const bytes=()=>[...cache.values()].reduce((sum,v)=>sum+v.image.width*v.image.height*4,0);while(cache.size>1&&(cache.size>24||bytes()>128*1024*1024)){const first=[...cache.keys()].find(key=>key!==state.info?.frame.id);if(!first)break;cache.delete(first);}invalidate();}
async function resource(frame){
  if(!frame)return null;if(cached(frame.id))return cached(frame.id);if(pending.has(frame.id))return pending.get(frame.id);
  const task=(async()=>{const info=await api('/api/open?id='+frame.id);const image=await loadImage(info.image);const item={info,image};remember(frame.id,item);return item;})();
  pending.set(frame.id,task);try{return await task;}finally{pending.delete(frame.id);}
}
function origin(width,height,offset=[0,0]){
  const mode=$('alignment').value;
  return [(mode==='origin'?0:-width/2)+offset[0],(mode==='feet'?-height:mode==='center'?-height/2:0)+offset[1]];
}
function drawAt(context,image,offset=[0,0]){const [x,y]=origin(image.width,image.height,offset);context.drawImage(image,x,y);}
function background(context,width,height){
  const matte=$('matte').value;context.fillStyle=matte==='checker'?'#242932':matte;context.fillRect(0,0,width,height);
  if(matte==='checker'){context.fillStyle='#2e343e';const step=16;for(let y=0;y<height;y+=step)for(let x=0;x<width;x+=step)if((x/step+y/step)%2===0)context.fillRect(x,y,step,step);}
}
function ghost(frame,color){
  const item=frame&&cached(frame.id);if(!item)return;
  tint.width=item.image.width;tint.height=item.image.height;tc.globalCompositeOperation='source-over';tc.drawImage(item.image,0,0);tc.globalCompositeOperation='source-in';tc.fillStyle=color;tc.fillRect(0,0,tint.width,tint.height);tc.globalCompositeOperation='source-over';
  ctx.globalAlpha=+$('onionOpacity').value/100;drawAt(ctx,tint,item.info.offset);ctx.globalAlpha=1;
}
function render(){
  state.dirtyView=false;const w=view.width,h=view.height;background(ctx,w,h);
  if(!state.info)return;
  const cx=w/2+state.pan[0],cy=h/2+state.pan[1];ctx.save();ctx.translate(cx,cy);ctx.scale(state.zoom,state.zoom);ctx.imageSmoothingEnabled=state.zoom<3;
  if(!state.compare&&$('onion').checked){if($('prevGhost').checked)ghost(state.sequence[state.index-1],'#ff719e');if($('nextGhost').checked)ghost(state.sequence[state.index+1],'#62d8ef');}
  const [x,y]=origin(pixels.width,pixels.height,state.offset);
  ctx.strokeStyle='#ffffff2b';ctx.lineWidth=1/state.zoom;ctx.strokeRect(x,y,pixels.width,pixels.height);
  if(state.compare){drawAt(ctx,state.base,state.offset);ctx.save();const cut=(w*(+$('split').value/100)-cx)/state.zoom;ctx.beginPath();ctx.rect(cut,-h/state.zoom*30,w/state.zoom*40,h/state.zoom*60);ctx.clip();drawAt(ctx,pixels,state.offset);ctx.restore();}
  else drawAt(ctx,pixels,state.offset);
  ctx.restore();
  if(state.compare){const cut=w*(+$('split').value/100);ctx.strokeStyle='#d5ed9a';ctx.beginPath();ctx.moveTo(cut,0);ctx.lineTo(cut,h);ctx.stroke();}
  if(state.cursor&&!state.compare&&['brush','erase'].includes(state.tool)){
    ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.beginPath();ctx.arc(...state.cursor,Math.max(2,+$('size').value*state.zoom/2),0,Math.PI*2);ctx.stroke();ctx.strokeStyle='#000';ctx.lineWidth=1;ctx.beginPath();ctx.arc(...state.cursor,Math.max(3,+$('size').value*state.zoom/2+1),0,Math.PI*2);ctx.stroke();
  }
  $('zoom').textContent=Math.round(state.zoom*100)+'%';
}
function resize(){const r=$('viewport').getBoundingClientRect();view.width=Math.round(r.width);view.height=Math.round(r.height);invalidate();}
new ResizeObserver(resize).observe($('viewport'));
function fit(){if(!state.info)return;state.zoom=Math.min((view.width-100)/pixels.width,(view.height-90)/pixels.height,4);const o=origin(pixels.width,pixels.height,state.offset);state.pan=[-(o[0]+pixels.width/2)*state.zoom,-(o[1]+pixels.height/2)*state.zoom];invalidate();}
function snapshot(){return {image:paint.getImageData(0,0,pixels.width,pixels.height),offset:[...state.offset]};}
function limitHistory(stack){const max=Math.max(1,Math.min(30,Math.floor(96*1024*1024/(pixels.width*pixels.height*4))));while(stack.length>max)stack.shift();}
function checkpoint(){state.undo.push(snapshot());limitHistory(state.undo);state.redo=[];}
function changed(){state.version++;status();invalidate();}
function restoreUndoSnapshot(back){if(state.busy||state.pointer||!state.info)return;const from=back?state.undo:state.redo,to=back?state.redo:state.undo;if(!from.length)return;to.push(snapshot());limitHistory(to);const saved=from.pop();paint.putImageData(saved.image,0,0);state.offset=saved.offset;syncOffset();changed();}
function syncOffset(){$('offsetX').value=state.offset[0];$('offsetY').value=state.offset[1];}
async function save(){
  if(state.saving){await state.saving;if(dirty())return save();return;}
  if(!dirty()||state.pointer)return;
  const current=state.info,id=current.frame.id,version=state.version,offset=[...state.offset],png=pixels.toDataURL('image/png');
  state.saving=(async()=>{const result=await api('/api/save',{id,revision:current.revision,png,offset});current.revision=result.revision;current.offset=offset;state.saved=version;cache.delete(id);message('Retoque guardado · '+result.saved);await refreshHistory();})();status();
  try{await state.saving;}catch(e){message(e.message,true);throw e;}finally{state.saving=null;status();}
}
async function refreshHistory(){if(!state.info)return;const id=state.info.frame.id,result=await api('/api/history?id='+id);if(state.info?.frame.id!==id)return;const select=$('history');select.replaceChildren(new Option('Historial de este cuadro',''));result.items.forEach((name,i)=>select.add(new Option('Versión anterior '+(i+1)+' · '+new Date(Number(name.split('-')[0])/1e6).toLocaleString(),name)));}
function title(){const f=state.info.frame;$('title').textContent=f.name;$('title').title=f.path;$('dimensions').textContent=`${pixels.width} × ${pixels.height} px · ${f.category}`;$('frameCounter').textContent=`${state.index+1} / ${state.sequence.length}`;}
async function navigate(index,sequence=null){
  if(state.busy||state.pointer)return;const next=sequence||state.sequence;if(index<0||index>=next.length)return;
  state.busy=true;status();message('Abriendo cuadro…');
  try{
    await save();const item=await resource(next[index]);const base=await loadImage(item.info.original);
    if(sequence){state.sequence=sequence;state.playing=false;state.playIndex=0;$('play').textContent='▶ Reproducir';$('rangeStart').value=1;$('rangeEnd').value=Math.min(sequence.length,12);$('rangeStart').max=$('rangeEnd').max=sequence.length;buildTimeline();}
    state.index=index;state.info={...item.info};state.base=base;pixels.width=item.image.width;pixels.height=item.image.height;paint.clearRect(0,0,pixels.width,pixels.height);paint.drawImage(item.image,0,0);state.offset=[...item.info.offset];syncOffset();state.undo=[];state.redo=[];state.version=state.saved=0;state.playIndex=index;
    $('empty').hidden=true;title();fit();highlight();await refreshHistory();
    for(const f of [next[index-1],next[index+1]])if(f)resource(f).catch(()=>{});
    message('Pintá sobre el lienzo. Guardar conserva el original y crea un retoque local.');
  }catch(e){message(e.message,true);}finally{state.busy=false;status();invalidate();}
}
function buildTimeline(){
  const fragment=document.createDocumentFragment();state.sequence.forEach((frame,i)=>{const b=document.createElement('button');b.className='thumb';b.title=frame.name;b.dataset.index=i;const img=document.createElement('img');img.loading='lazy';img.src='/api/image?id='+frame.id;img.alt='';img.onerror=()=>{img.style.opacity='.2';};const label=document.createElement('span');label.textContent=frame.number;b.append(img,label);b.onclick=()=>navigate(i);fragment.append(b);});$('timeline').replaceChildren(fragment);
}
function highlight(){for(const b of $('timeline').children)b.classList.toggle('active',+b.dataset.index===state.index);const b=$('timeline').children[state.index];if(b){b.scrollIntoView({block:'nearest',inline:'nearest'});const img=b.querySelector('img');img.src='/api/image?id='+state.info.frame.id+'&v='+(state.info.revision||'base');}for(const b of $('groups').children)b.classList.toggle('active',b.dataset.group===state.info.frame.group);}
function drawGroups(){
  const term=$('search').value.toLowerCase(),category=$('category').value,fragment=document.createDocumentFragment();
  state.groups.filter(g=>(!category||g[0].category===category)&&g.some(f=>f.name.toLowerCase().includes(term))).forEach(group=>{const b=document.createElement('button');b.className='group';b.dataset.group=group[0].group;const strong=document.createElement('strong'),small=document.createElement('small');strong.textContent=group[0].group.split('/').slice(1).join('/');small.textContent=group[0].category+' · '+group.length+' cuadros';b.append(strong,small);b.onclick=()=>navigate(0,group);b.classList.toggle('active',group[0].group===state.info?.frame.group);fragment.append(b);});$('groups').replaceChildren(fragment);
}
let catalogRequest=null;
function catalog(){if(catalogRequest)return catalogRequest;catalogRequest=loadCatalog().finally(()=>catalogRequest=null);return catalogRequest;}
async function loadCatalog(){const result=await api('/api/catalog');state.catalogCursor=result.cursor;const known=new Map(state.frames.map(f=>[f.id,f]));state.frames=result.frames.map(f=>known.has(f.id)?Object.assign(known.get(f.id),f):f);const groups=new Map();for(const f of state.frames){if(!groups.has(f.group))groups.set(f.group,[]);groups.get(f.group).push(f);}state.groups=[...groups.values()].map(g=>g.sort((a,b)=>a.number-b.number||a.name.localeCompare(b.name))).sort((a,b)=>a[0].group.localeCompare(b[0].group));const selected=$('category').value;$('category').replaceChildren(new Option('Todas las colecciones',''));[...new Set(result.frames.map(f=>f.category))].sort().forEach(c=>$('category').add(new Option(c,c)));$('category').value=selected;drawGroups();message(result.frames.length?`${result.frames.length} recursos · ${state.groups.length} secuencias · Elegí una o importá PNG.`:'Importá uno o varios PNG para empezar.');return result;}
function chooseTool(tool){state.tool=tool;document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('selected',b.dataset.tool===tool));view.style.cursor=tool==='hand'?'grab':tool==='picker'?'copy':'crosshair';invalidate();}
function position(event){const r=view.getBoundingClientRect(),sx=event.clientX-r.left,sy=event.clientY-r.top;const o=origin(pixels.width,pixels.height,state.offset);return {x:(sx-view.width/2-state.pan[0])/state.zoom-o[0],y:(sy-view.height/2-state.pan[1])/state.zoom-o[1],sx,sy,p:event.pointerType==='pen'&&$('pressure').checked?Math.max(.02,event.pressure):1};}
function dab(point,erase){
  const radius=Math.max(.25,+$('size').value*point.p/2);paint.save();paint.globalCompositeOperation=erase?'destination-out':$('alphaLock').checked?'source-atop':'source-over';paint.globalAlpha=+$('opacity').value/100;
  const color=$('color').value,hard=+$('hardness').value/100;
  if(hard>=.99){paint.fillStyle=erase?'#000':color;}else{const g=paint.createRadialGradient(point.x,point.y,radius*hard,point.x,point.y,radius);const rgb=erase?'0,0,0':`${parseInt(color.slice(1,3),16)},${parseInt(color.slice(3,5),16)},${parseInt(color.slice(5,7),16)}`;g.addColorStop(0,`rgba(${rgb},1)`);g.addColorStop(1,`rgba(${rgb},0)`);paint.fillStyle=g;}
  paint.beginPath();paint.arc(point.x,point.y,radius,0,Math.PI*2);paint.fill();paint.restore();
}
function stroke(from,to,erase){const distance=Math.hypot(to.x-from.x,to.y-from.y);const spacing=Math.max(.3,+$('size').value*Math.min(from.p,to.p)*.13);const count=Math.max(1,Math.ceil(distance/spacing));for(let i=1;i<=count;i++){const t=i/count;dab({x:from.x+(to.x-from.x)*t,y:from.y+(to.y-from.y)*t,p:from.p+(to.p-from.p)*t},erase);}}
view.addEventListener('pointerdown',event=>{
  if(event.pointerType==='touch'||state.busy||!state.info||state.pointer)return;event.preventDefault();const p=position(event);
  if(state.space||state.tool==='hand'||event.button===1){state.pointer={id:event.pointerId,mode:'pan',last:p};view.setPointerCapture(event.pointerId);return;}
  if(state.tool==='picker'||event.altKey||event.button===2){if(p.x>=0&&p.y>=0&&p.x<pixels.width&&p.y<pixels.height){const rgba=paint.getImageData(Math.floor(p.x),Math.floor(p.y),1,1).data;if(rgba[3]){$('color').value='#'+[...rgba.slice(0,3)].map(c=>c.toString(16).padStart(2,'0')).join('');updateControls();}else message('Ese píxel es transparente.');}return;}
  if(state.compare){message('Desactivá Antes / después para pintar.');return;}
  if(p.x<0||p.y<0||p.x>=pixels.width||p.y>=pixels.height)return;
  checkpoint();const erase=state.tool==='erase'||event.button===5||(event.buttons&32)!==0;state.pointer={id:event.pointerId,mode:'paint',last:p,erase};view.setPointerCapture(event.pointerId);dab(p,erase);changed();
});
view.addEventListener('pointermove',event=>{
  if(event.pointerType==='touch')return;const p=position(event);state.cursor=[p.sx,p.sy];
  if(event.pointerType==='pen')$('penState').textContent='Lápiz detectado · presión '+Math.round(event.pressure*100)+'%';
  const current=state.pointer;if(current&&current.id===event.pointerId){if(current.mode==='pan'){state.pan[0]+=p.sx-current.last.sx;state.pan[1]+=p.sy-current.last.sy;current.last=p;}else{const events=event.getCoalescedEvents?.()||[];for(const e of events.length?events:[event]){const q=position(e);stroke(current.last,q,current.erase);current.last=q;}}}invalidate();
});
function endPointer(event){if(state.pointer?.id!==event.pointerId)return;state.pointer=null;if(view.hasPointerCapture(event.pointerId))view.releasePointerCapture(event.pointerId);status();invalidate();}
view.addEventListener('pointerup',endPointer);view.addEventListener('pointercancel',endPointer);view.addEventListener('lostpointercapture',endPointer);view.addEventListener('pointerleave',()=>{state.cursor=null;invalidate();});view.addEventListener('contextmenu',e=>e.preventDefault());
view.addEventListener('wheel',event=>{event.preventDefault();if(!state.info)return;const p=position(event),old=state.zoom;state.zoom=Math.max(.03,Math.min(40,old*Math.exp(-event.deltaY*.0015)));const cx=p.sx-view.width/2,cy=p.sy-view.height/2;state.pan=[cx-(cx-state.pan[0])*state.zoom/old,cy-(cy-state.pan[1])*state.zoom/old];invalidate();},{passive:false});
function previewRange(){const last=state.sequence.length-1;const a=Math.min(last,Math.max(0,(+$('rangeStart').value||1)-1));const b=Math.max(a,Math.min(last,(+$('rangeEnd').value||1)-1));return [a,b];}
function previewDraw(now){
  background(pc,preview.width,preview.height);if(!state.info)return;
  const [a,b]=previewRange();if(state.playing&&now-state.playTime>=1000/Math.min(60,Math.max(1,+$('fps').value||12))){const candidate=state.playIndex<a||state.playIndex>=b?a:state.playIndex+1;const f=state.sequence[candidate];if(f&&(f.id===state.info.frame.id||cached(f.id))){state.playTime=now;state.playIndex=candidate;}else if(f)resource(f).catch(()=>{});}
  const i=state.playing?state.playIndex:state.index,frame=state.sequence[i];if(!frame)return;
  let image,offset;if(frame.id===state.info.frame.id){image=pixels;offset=state.offset;}else{const item=cached(frame.id);if(item){image=item.image;offset=item.info.offset;}else{resource(frame).catch(e=>{state.playing=false;$('play').textContent='▶ Reproducir';message(e.message,true);});return;}}
  // Fixed scale across the sequence, so cropped frames do not pump in size.
  const dims=state.sequence.slice(a,b+1).map(f=>f.dimensions||[pixels.width,pixels.height]);const maxW=Math.max(pixels.width,...dims.map(d=>d[0])),maxH=Math.max(pixels.height,...dims.map(d=>d[1]));const scale=Math.min((preview.width-30)/maxW,(preview.height-35)/maxH);
  const mode=$('alignment').value;pc.save();pc.translate(mode==='origin'?15:preview.width/2,mode==='feet'?preview.height-18:mode==='center'?preview.height/2:15);pc.scale(scale,scale);pc.imageSmoothingEnabled=true;drawAt(pc,image,offset);pc.restore();pc.fillStyle='#d5ed9a';pc.font='10px Segoe UI';pc.fillText(`${i+1} / ${state.sequence.length}`,8,14);
  if(state.playing){const next=state.sequence[i>=b?a:i+1];if(next)resource(next).catch(()=>{});}
}
let previewAt=0;function tick(now){if(state.dirtyView)render();if(now-previewAt>30){previewDraw(now);previewAt=now;}requestAnimationFrame(tick);}requestAnimationFrame(tick);
function updateControls(){for(const [id,suffix] of [['size',' px'],['opacity','%'],['hardness','%']])$(id+'Value').textContent=$(id).value+suffix;$('onionValue').textContent=$('onionOpacity').value+'%';$('colorHex').textContent=$('color').value;invalidate();try{localStorage.setItem('monkey-painter-settings',JSON.stringify(Object.fromEntries(preferences.map(id=>[id,$(id).type==='checkbox'?$(id).checked:$(id).value]))));}catch{}}
try{const settings=JSON.parse(localStorage.getItem('monkey-painter-settings')||'{}');for(const id of preferences)if(id in settings){if($(id).type==='checkbox')$(id).checked=!!settings[id];else $(id).value=settings[id];}}catch{}
for(const id of preferences)$(id).addEventListener('input',updateControls);updateControls();
for(const color of ['#171921','#f3eee0','#c8605f']){const b=document.createElement('button');b.style.background=color;b.title=color;b.onclick=()=>{$('color').value=color;updateControls();};$('swatches').append(b);}
document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>chooseTool(b.dataset.tool));
$('save').onclick=()=>save().catch(()=>{});$('undo').onclick=()=>restoreUndoSnapshot(true);$('redo').onclick=()=>restoreUndoSnapshot(false);$('previous').onclick=()=>navigate(state.index-1);$('next').onclick=()=>navigate(state.index+1);$('fit').onclick=fit;$('actual').onclick=()=>{state.zoom=1;invalidate();};
$('compare').onclick=()=>{state.compare=!state.compare;$('compare').classList.toggle('active',state.compare);$('split').hidden=$('compareLabels').hidden=!state.compare;invalidate();};$('split').oninput=invalidate;
$('play').onclick=()=>{if(!state.info)return;state.playing=!state.playing;state.playIndex=previewRange()[0];state.playTime=performance.now();$('play').textContent=state.playing?'Ⅱ Pausar':'▶ Reproducir';};
for(const id of ['offsetX','offsetY'])$(id).onchange=()=>{if(!state.info||state.busy)return;checkpoint();state.offset=[Math.max(-16384,Math.min(16384,+$('offsetX').value||0)),Math.max(-16384,Math.min(16384,+$('offsetY').value||0))];changed();};
$('search').oninput=drawGroups;$('category').onchange=drawGroups;
$('export').onclick=()=>{if(!state.info)return;const link=document.createElement('a');link.download=state.info.frame.name+'-retocado.png';link.href=pixels.toDataURL('image/png');link.click();};
$('reset').onclick=()=>{if(!state.info||state.busy)return;checkpoint();paint.clearRect(0,0,pixels.width,pixels.height);paint.drawImage(state.base,0,0);changed();message('PNG base recuperado en el lienzo. Podés deshacer o guardar como nuevo retoque.');};
$('restore').onclick=async()=>{if(!state.info||state.busy||!$('history').value)return;state.busy=true;status();try{const image=await loadImage('/api/version?id='+state.info.frame.id+'&name='+encodeURIComponent($('history').value));checkpoint();paint.clearRect(0,0,pixels.width,pixels.height);paint.drawImage(image,0,0);changed();message('Versión cargada. Guardá para crear un nuevo retoque.');}catch(e){message(e.message,true);}finally{state.busy=false;status();}};
$('importButton').onclick=()=>{if(!state.busy)$('import').click();};$('import').onchange=async event=>{
  if(state.busy)return;state.busy=true;status();const batch='lote-'+Date.now();let first=null;
  try{await save();for(const file of event.target.files){message('Importando '+file.name+'…');const png=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file);});const result=await api('/api/import',{name:file.name,png,batch});first??=result.id;}await catalog();const f=state.frames.find(f=>f.id===first);if(f){$('category').value=f.category;drawGroups();state.busy=false;await navigate(0,state.groups.find(g=>g[0].group===f.group));}}catch(e){message(e.message||'No se pudo importar.',true);}finally{state.busy=false;event.target.value='';status();}
};
window.addEventListener('keydown',event=>{
  const typing=/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName),key=event.key.toLowerCase(),mod=event.ctrlKey||event.metaKey;
  if(mod&&key==='s'){event.preventDefault();save().catch(()=>{});return;}
  if(typing)return;
  if(mod&&(key==='z'||key==='y')){event.preventDefault();restoreUndoSnapshot(key==='z'&&!event.shiftKey);return;}
  if(key===' '){event.preventDefault();state.space=true;return;}
  if(mod)return;
  if({b:'brush',e:'erase',i:'picker',h:'hand'}[key])chooseTool({b:'brush',e:'erase',i:'picker',h:'hand'}[key]);
  if(key==='f')fit();if(key==='a'||key==='arrowleft'){event.preventDefault();navigate(state.index-1);}if(key==='d'||key==='arrowright'){event.preventDefault();navigate(state.index+1);}
  if(key==='['||key===']'){$('size').value=Math.max(1,Math.min(200,+$('size').value+(key==='['?-2:2)));updateControls();}
});
window.addEventListener('keyup',event=>{if(event.key===' ')state.space=false;});window.addEventListener('blur',()=>{state.space=false;state.pointer=null;});window.addEventListener('beforeunload',event=>{if(dirty()||state.saving){event.preventDefault();event.returnValue='';}});
catalog().catch(e=>message(e.message,true));status();
