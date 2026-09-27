'use strict';
async function showDeliveries(){
  const dialog=document.createElement('dialog');dialog.className='imagelab-dialog delivery-dialog';
  dialog.innerHTML=`<div class="il-heading"><strong>Entrega del barco</strong><button data-close aria-label="Cerrar entregas">Cerrar</button></div>
    <p>Versiones en uso, aprobaciones vigentes y controles de forma, color y bordes. Los avisos automáticos requieren revisión visual.</p>
    <div class="delivery-toolbar"><label>Alcance<select data-scope><option value="complete">Barco + agua + inventario + dependencias</option><option value="interior">Interior del barco + dependencias</option></select></label><button data-prepare>Preparar / volver a analizar</button></div>
    <p data-status role="status"></p><p data-summary></p>
    <div class="delivery-toolbar"><label>Rama<input data-name value="scene-1-ship-v1" aria-label="Nombre de rama de entrega"></label><button data-branch disabled>Crear rama revisada</button><button data-draft disabled>Crear rama como borrador</button><button data-push disabled>Enviar rama</button></div>
    <p data-result></p><label>Mostrar<select data-filter><option value="pending">Pendientes</option><option value="water">Agua</option><option value="halo">Halos / bordes</option><option value="approval">Sin aprobación vigente</option><option value="ready">Listos</option><option value="all">Todos</option></select></label><div data-items class="delivery-items"></div>`;
  document.body.append(dialog);dialog.showModal();const q=k=>dialog.querySelector('[data-'+k+']');let timer,report,signature='',working=false;
  const close=()=>{clearTimeout(timer);dialog.close();dialog.remove();};q('close').onclick=close;dialog.oncancel=e=>{e.preventDefault();close();};
  function render(){
    const r=report;if(!r)return;q('summary').textContent=r.error||`${r.items?.length||0} assets · ${r.ready||0} listos · ${r.blocked||0} pendientes. ${r.scope==='complete'?'Incluye agua y dependencias.':''}`;
    q('result').textContent=r.branch?`${r.branch} · ${r.commit.slice(0,8)} · ${r.pushed?'Enviada':'Local'} · ${r.delivery_state==='draft'?'BORRADOR: quedan revisiones pendientes':'Revisada'}`:'';
    q('branch').disabled=working||r.status!=='ready'||!!r.branch;q('draft').disabled=working||!['ready','blocked'].includes(r.status)||!!r.branch;q('push').disabled=working||!r.branch||r.pushed;
    q('items').replaceChildren();const filter=q('filter').value;
    const items=(r.items||[]).filter(i=>filter==='all'||(filter==='pending'?i.issues.length:filter==='water'?i.name.includes('LFLF_0011_')||i.name.startsWith('0011_'):filter==='halo'?i.issues.some(s=>/halo|Borde|alpha/i.test(s)):filter==='approval'?!i.approved:!i.issues.length));
    for(const item of items){const row=document.createElement('div');row.className='delivery-row';const title=document.createElement('strong');title.textContent=item.name;const status=document.createElement('small');status.textContent=item.issues.join(' · ')||'Aprobado y controles sin alertas';status.style.color=item.issues.length?'#eac264':'#77ce98';const open=document.createElement('button');open.textContent='Revisar';open.onclick=async()=>{await catalog();const frame=state.frames.find(f=>f.id===item.id);if(!frame){q('status').textContent='Asset no disponible en el catálogo.';return;}close();await openAssetReview(frame);};row.append(title,status,open);q('items').append(row);}
    if(!items.length)q('items').textContent='No hay assets en este filtro.';
    if(r.missing_sources?.length){const p=document.createElement('p');p.textContent='Fuentes ausentes: '+r.missing_sources.join(', ');q('items').prepend(p);}
  }
  q('filter').onchange=render;
  async function refresh(){clearTimeout(timer);if(!dialog.isConnected)return;try{const s=await api('/api/deliveries');if(!dialog.isConnected)return;report=s.report;q('status').textContent=s.progress.running?`Analizando ${s.progress.done} / ${s.progress.total}…`:'Sin generaciones ni créditos. El informe guarda una copia de los assets exportables.';q('prepare').disabled=working||s.progress.running;const next=JSON.stringify(s);if(next!==signature){signature=next;render();}}catch(e){q('status').textContent=e.message;}if(dialog.isConnected)timer=setTimeout(refresh,2000);}
  async function action(path,body){working=true;for(const b of dialog.querySelectorAll('button:not([data-close])'))b.disabled=true;q('status').textContent='Preparando…';try{await api(path,body);signature='';}catch(e){q('result').textContent=e.message;}finally{working=false;await refresh();}}
  q('prepare').onclick=()=>action('/api/deliveries/prepare',{scope:q('scope').value});
  q('branch').onclick=()=>action('/api/deliveries/branch',{id:report.id,name:q('name').value});
  q('draft').onclick=()=>action('/api/deliveries/branch',{id:report.id,name:q('name').value,draft:true});
  q('push').onclick=()=>action('/api/deliveries/push',{id:report.id});
  await refresh();
}
