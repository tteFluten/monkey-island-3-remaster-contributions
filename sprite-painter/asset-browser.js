'use strict';
// A virtual canvas: only visible cards are painted and at most six thumbnails load together.
const assetGrid = (() => {
  let panel, canvas, ctx, collection, search, filter, order, statusLine, zoomLabel, actionLayer;
  let items=[], cols=4, scale=1, panX=18, panY=18, width=0, height=0, active=false, opening=false, selected=-1;
  const CW=340, CH=312, cache=new Map(), loading=new Set(), queue=[], actions=new Map();
  let running=0, scheduled=false, drag=null;
  function invalidate(){if(!active||scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;if(active)draw();});}
  window.addEventListener('imagelab-assets',invalidate);
  function trim(){while(cache.size>192){const key=cache.keys().next().value;cache.get(key)?.close?.();cache.delete(key);}}
  function request(frame,reference,result=null){
    const key=frame.id+(reference?'/original':result?'/result/'+result.id:'/edit/'+(frame.revision||'base'));
    if(cache.has(key)){const value=cache.get(key);cache.delete(key);cache.set(key,value);return value;}
    if(!loading.has(key)){loading.add(key);queue.push({key,frame,reference,result});}
    return undefined;
  }
  function pump(){while(running<6&&queue.length){
    const task=queue.shift();running++;
    fetch(task.result?.image||('/api/thumbnail?id='+task.frame.id+'&reference='+(task.reference?1:0)+'&v='+(task.frame.revision||'base'))).then(async response=>{
      if(!response.ok)throw new Error('PNG no disponible');
      return createImageBitmap(await response.blob());
    }).then(bitmap=>{cache.set(task.key,bitmap);trim();}).catch(()=>cache.set(task.key,null)).finally(()=>{loading.delete(task.key);running--;invalidate();pump();});
  }}
  function text(value,x,y,max,color='#d7dce2',size=11){ctx.fillStyle=color;ctx.font=size+'px Segoe UI';let label=String(value);while(ctx.measureText(label).width>max&&label.length>3)label=label.slice(0,-2);if(label!==String(value))label+='…';ctx.fillText(label,x,y);}
  function picture(bitmap,x,y,w,h,reference){
    ctx.fillStyle='#232a32';ctx.fillRect(x,y,w,h);ctx.fillStyle='#29313b';
    for(let row=0;row<h/10;row++)for(let col=0;col<w/10;col++)if((row+col)%2===0)ctx.fillRect(x+col*10,y+row*10,Math.min(10,w-col*10),Math.min(10,h-row*10));
    if(bitmap){const ratio=Math.min((w-12)/bitmap.width,(h-12)/bitmap.height);ctx.imageSmoothingEnabled=!reference;ctx.drawImage(bitmap,x+(w-bitmap.width*ratio)/2,y+(h-bitmap.height*ratio)/2,bitmap.width*ratio,bitmap.height*ratio);}
    else text(bitmap===null?'No disponible':'Cargando…',x+10,y+h/2,w-20,'#8491a1',10);
  }
  function draw(){
    const dpr=Math.min(devicePixelRatio||1,2);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#11151a';ctx.fillRect(0,0,width,height);
    ctx.save();ctx.translate(panX,panY);ctx.scale(scale,scale);
    const first=Math.max(0,Math.floor(-panY/scale/CH)),last=Math.min(Math.ceil(items.length/cols),Math.ceil((height-panY)/scale/CH));
    // Drop requests that have not started when the user pans elsewhere.
    for(const task of queue.splice(0))loading.delete(task.key);
    let visible=0;
    const visibleActions=new Set();
    for(let row=first;row<last;row++)for(let col=0;col<cols;col++){
      const i=row*cols+col;if(i>=items.length)break;
      const x=col*CW,y=row*CH;if(x*scale+panX>width||(x+CW)*scale+panX<0)continue;
      visible++;const frame=items[i],review=reviewInfo(frame),accent=review.priority===2?'#ef8176':review.priority===1?'#dfbc76':'#7c8a99';
      ctx.fillStyle='#1b2129';ctx.fillRect(x,y,CW-14,CH-14);ctx.strokeStyle=i===selected?'#cee7a5':'#333d49';ctx.lineWidth=i===selected?2:1;ctx.strokeRect(x+.5,y+.5,CW-15,CH-15);
      text(frame.name,x+12,y+21,CW-40,'#e4e8ed',12);
      const job=imageLabAssetJobs.get(frame.id),approved=imageLabApprovals[frame.id];
      const result=!frame.edited&&job?.status==='ready'&&job.image?job:null;
      text(frame.reference_kind==='original-preparado'?'ORIGINAL · ALFA LIMPIO':'ORIGINAL',x+12,y+40,145,'#8e9aa9',9);text(frame.edited?'EN USO':result?'PROPUESTA · SIN APLICAR':'REMASTER',x+171,y+40,145,'#c5d6af',9);
      picture(frame.has_reference?request(frame,true):null,x+10,y+48,149,132,true);
      picture(request(frame,false,result),x+167,y+48,149,132,false);
      const pending=job&&['queued','running'].includes(job.status);
      const badge=pending?(job.status==='queued'?'◷ EN COLA':'◉ GENERANDO'):approved?'✓ APROBADO':frame.edited?'✓ VERSIÓN EN USO':job?.quality?.passed===false?'! PROPUESTA CON ALERTAS':job?.status==='ready'?'VARIANTE PARA REVISAR':job&&['failed','interrupted'].includes(job.status)?'! ERROR · VER COLA':null;
      if(badge){const color=pending?'#7abfff':approved?'#a8dc82':'#e8c67c';ctx.strokeStyle=color;ctx.lineWidth=2;ctx.strokeRect(x+1,y+1,CW-16,CH-16);ctx.fillStyle='#121c29';ctx.fillRect(x+10,y+156,306,24);text(badge,x+17,y+172,290,color,11);}
      ctx.fillStyle=accent;ctx.beginPath();ctx.arc(x+15,y+197,3,0,Math.PI*2);ctx.fill();
      text(review.text,x+25,y+201,CW-50,accent,10);
      text(frame.category+' · cuadro '+frame.number,x+12,y+218,CW-36,'#8491a1',10);
      if(scale>=.5){
        visibleActions.add(frame.id);
        let buttons=actions.get(frame.id);
        if(!buttons){
          buttons=document.createElement('div');buttons.className='ab-card-actions';
          const reviewButton=document.createElement('button');reviewButton.className='ab-review';reviewButton.textContent='Comparar y crear versiones';reviewButton.setAttribute('aria-label','Comparar asset: '+frame.name);
          reviewButton.onclick=()=>edit(items.findIndex(f=>f.id===frame.id));
          const approveButton=document.createElement('button');approveButton.className='ab-approve';
          approveButton.onclick=async()=>{approveButton.disabled=true;try{await approveImageLabAsset(frame);}finally{approveButton.disabled=false;invalidate();}};
          buttons.append(reviewButton,approveButton);actionLayer.append(buttons);actions.set(frame.id,buttons);
        }
        const approveButton=buttons.querySelector('.ab-approve');
        approveButton.textContent=approved?'✓ Aprobado · quitar aprobación':'✓ Aprobar · está bien';
        approveButton.setAttribute('aria-label',(approved?'Quitar aprobación: ':'Aprobar asset: ')+frame.name);
        approveButton.setAttribute('aria-pressed',String(!!approved));
        buttons.style.transform=`translate(${x*scale+panX+10*scale}px,${(y+228)*scale+panY}px) scale(${scale})`;
      }
    }
    for(const [id,buttons] of actions)if(!visibleActions.has(id)){buttons.remove();actions.delete(id);}
    ctx.restore();pump();zoomLabel.textContent=Math.round(scale*100)+'%';
    if(!items.length){text('No hay assets con estos filtros.',30,60,width-60,'#bac4d0',16);}
    statusLine.textContent=items.length+' assets · '+visible+' visibles · clic para comparar · arrastrar para mover · Ctrl + rueda para zoom';
  }
  function resize(){const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);invalidate();}
  function fit(){cols=Math.max(1,Math.min(8,Math.floor(width/300)));scale=Math.min(1.25,(width-36)/(cols*CW));panX=18;panY=18;invalidate();}
  function zoom(factor,x=width/2,y=height/2){const previous=scale;scale=Math.max(.25,Math.min(3,scale*factor));panX=x-(x-panX)*scale/previous;panY=y-(y-panY)*scale/previous;invalidate();}
  function rebuild(){
    const term=search.value.trim().toLowerCase();
    items=state.frames.filter(f=>(!collection.value||f.category===collection.value)&&(!term||(f.name+' '+f.category).toLowerCase().includes(term))&&
      (filter.value==='all'||filter.value==='issues'&&reviewInfo(f).priority>0||filter.value==='rejected'&&reviewInfo(f).priority===2||filter.value==='unreviewed'&&!f.review||filter.value==='edited'&&f.edited));
    const silhouette=f=>f.review?.current&&Number.isFinite(f.review.validation?.silhouette_iou)?f.review.validation.silhouette_iou:2;
    items.sort((a,b)=>order.value==='priority'?(reviewInfo(b).priority-reviewInfo(a).priority||silhouette(a)-silhouette(b)||a.group.localeCompare(b.group)||a.number-b.number):(a.group.localeCompare(b.group)||a.number-b.number));
    selected=-1;panY=18;invalidate();
  }
  function hit(x,y){const wx=(x-panX)/scale,wy=(y-panY)/scale;if(wx<0||wy<0)return -1;const col=Math.floor(wx/CW),row=Math.floor(wy/CH);if(col>=cols||wx%CW>CW-14||wy%CH>CH-14)return -1;const i=row*cols+col;return i<items.length?i:-1;}
  async function edit(index){
    if(index<0||opening)return;opening=true;selected=index;invalidate();const frame=items[index];
    try{await save();await openAssetReview(frame);}
    catch(error){statusLine.textContent=error.message;}finally{opening=false;}
  }

  function create(){
    panel=document.createElement('section');panel.className='asset-browser';
    panel.innerHTML='<div class="ab-header"><div><strong>ASSETS</strong><small>Original y remaster · mesa de revisión</small></div><input data-search type="search" placeholder="Buscar personaje, traje, cuadro…" aria-label="Buscar assets"><select data-collection aria-label="Colección de assets"></select><select data-filter aria-label="Estado de revisión"><option value="all">Todos los estados</option><option value="issues">Necesitan revisión</option><option value="rejected">Rechazados</option><option value="unreviewed">Sin evaluación</option><option value="edited">Con retoque</option></select><select data-order aria-label="Orden de assets"><option value="priority">Problemas primero</option><option value="name">Orden de secuencia</option></select><button data-close>Volver al taller</button></div><div class="ab-tools"><span>Rojo: rechazo registrado · ámbar: revisar · gris: sin alerta registrada</span><button data-minus aria-label="Alejar">−</button><output data-zoom></output><button data-plus aria-label="Acercar">+</button><button data-fit>Encuadrar</button></div><canvas tabindex="0" aria-label="Mesa de assets. Arrastrar para desplazar, Ctrl más rueda para zoom. Flechas para seleccionar y Enter para comparar."></canvas><div class="ab-status" role="status"></div>';
    document.body.append(panel);canvas=panel.querySelector('canvas');
    const queueButton=document.createElement('button');queueButton.textContent='Cola de trabajos';queueButton.dataset.imagelabQueue='';queueButton.onclick=showImageLabQueue;panel.querySelector('.ab-tools').append(queueButton);
    const stage=document.createElement('div');stage.className='ab-stage';canvas.replaceWith(stage);stage.append(canvas);actionLayer=document.createElement('div');actionLayer.className='ab-actions';stage.append(actionLayer);
    ctx=canvas.getContext('2d');search=panel.querySelector('[data-search]');collection=panel.querySelector('[data-collection]');filter=panel.querySelector('[data-filter]');order=panel.querySelector('[data-order]');zoomLabel=panel.querySelector('[data-zoom]');statusLine=panel.querySelector('.ab-status');
    order.title='Rechazos primero; luego borradores. Dentro de cada estado, menor coincidencia de silueta si hay una medición registrada.';
    search.oninput=rebuild;collection.onchange=rebuild;filter.onchange=rebuild;order.onchange=rebuild;
    panel.querySelector('[data-close]').onclick=()=>{panel.hidden=true;active=false;};panel.querySelector('[data-minus]').onclick=()=>zoom(1/1.2);panel.querySelector('[data-plus]').onclick=()=>zoom(1.2);panel.querySelector('[data-fit]').onclick=fit;
    canvas.onpointerdown=e=>{if(e.button!==0&&e.button!==1)return;canvas.focus();canvas.setPointerCapture(e.pointerId);drag={id:e.pointerId,x:e.offsetX,y:e.offsetY,lastX:e.offsetX,lastY:e.offsetY,moved:false};};
    canvas.onpointermove=e=>{if(!drag)return;const dx=e.offsetX-drag.lastX,dy=e.offsetY-drag.lastY;if(Math.hypot(e.offsetX-drag.x,e.offsetY-drag.y)>5)drag.moved=true;if(drag.moved){panX+=dx;panY+=dy;invalidate();}drag.lastX=e.offsetX;drag.lastY=e.offsetY;};
    canvas.onpointerup=e=>{if(!drag)return;const tap=!drag.moved;drag=null;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);if(tap&&e.button===0)edit(hit(e.offsetX,e.offsetY));};canvas.onpointercancel=()=>{drag=null;};
    canvas.addEventListener('wheel',e=>{e.preventDefault();if(e.ctrlKey||e.metaKey)zoom(Math.exp(-e.deltaY*.002),e.offsetX,e.offsetY);else{panX-=e.deltaX;panY-=e.deltaY;invalidate();}},{passive:false});
    canvas.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();edit(selected);return;}const delta={ArrowLeft:-1,ArrowRight:1,ArrowUp:-cols,ArrowDown:cols}[e.key];if(delta!=null){e.preventDefault();e.stopPropagation();selected=Math.max(0,Math.min(items.length-1,(selected<0?0:selected)+delta));panY=height/2-(Math.floor(selected/cols)*CH+CH/2)*scale;invalidate();}};
    new ResizeObserver(resize).observe(canvas);
  }
  async function open(){
    if(confiteSession)return;
    const returning=!!panel, savedView={panX,panY,scale};
    if(!panel)create();panel.hidden=false;active=true;statusLine.textContent='Cargando assets…';
    await catalog();
    if(state.info){const key=state.info.frame.id+'/edit';cache.get(key)?.close?.();cache.delete(key);}
    const previous=collection.value;collection.replaceChildren(new Option('Todas las colecciones',''));[...new Set(state.frames.map(f=>f.category))].sort().forEach(c=>collection.add(new Option(c,c)));collection.value=previous;
    if(!previous&&state.frames.some(f=>f.category==='Barco · personajes'))collection.value='Barco · personajes';
    resize();rebuild();if(returning){panX=savedView.panX;panY=savedView.panY;scale=savedView.scale;}else fit();invalidate();
  }
  return {open};
})();
async function openAssetBrowser(){try{await save();await assetGrid.open();}catch(error){message(error.message,true);}}
const assetBrowserButton=document.createElement('button');assetBrowserButton.textContent='Explorar assets';assetBrowserButton.className='accent';document.querySelector('header').insertBefore(assetBrowserButton,confiteButton);assetBrowserButton.onclick=openAssetBrowser;
window.addEventListener('load',openAssetBrowser,{once:true});
