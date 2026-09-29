'use strict';
// One push connection for the whole app, including changes from another window.
const LiveAssets=(()=>{
  let source=null,timer=null,retry=null,busy=false,full=false,started=false,connected=false,cursor=null,changeCursor=null;
  const pending=new Set(),jobs=new Map();
  function merge(snapshot){
    const ids=new Set(snapshot.ids),frames=new Map(state.frames.map(f=>[f.id,f]));
    const changed=[];
    for(const frame of snapshot.frames){
      const previous=frames.get(frame.id);
      if(!previous||previous.revision!==frame.revision||previous.thumbnail_version!==frame.thumbnail_version){changed.push(frame.id);cache.delete(frame.id);}
      if(previous)Object.assign(previous,frame);else{state.frames.push(frame);frames.set(frame.id,frame);}
    }
    // Sequence lists may still hold objects from an earlier catalog response.
    for(const group of state.groups)for(const frame of group){const latest=frames.get(frame.id);if(latest)Object.assign(frame,latest);}
    if(snapshot.full)jobs.clear();else for(const [id,job] of jobs)if(ids.has(job.asset_id))jobs.delete(id);
    for(const job of snapshot.jobs)jobs.set(job.id,job);
    const approvals=snapshot.full?{}:{...imageLabApprovals};
    for(const id of snapshot.ids){const value=snapshot.approvals[id];if(value)approvals[id]=value;else delete approvals[id];}
    const ordered=[...jobs.values()].sort((a,b)=>b.created_at-a.created_at);
    syncImageLabAssets(ordered,approvals);
    const pendingCount=ordered.filter(j=>['queued','running'].includes(j.status)).length;
    const readyCount=ordered.filter(j=>j.status==='ready'&&j.quality?.passed!==false).length;
    document.querySelectorAll('[data-imagelab-queue]').forEach(button=>button.textContent=`Cola de trabajos · ${pendingCount} pendientes · ${readyCount} para revisar`);
    window.dispatchEvent(new CustomEvent('assets-live',{detail:{ids:snapshot.ids,changed,full:snapshot.full}}));
  }
  async function flush(){
    clearTimeout(timer);timer=null;if(busy||document.hidden)return;
    if(!full&&!pending.size)return;
    const all=full;full=false;const ids=[...pending].slice(0,80);
    if(all)pending.clear();else ids.forEach(id=>pending.delete(id));
    busy=true;
    try{const snapshot=await api('/api/live-state'+(all?(cursor?'?since='+encodeURIComponent(cursor):''):'?ids='+encodeURIComponent(ids.join(','))));merge(snapshot);if(all)cursor=snapshot.cursor;}
    catch{if(all)full=true;else ids.forEach(id=>pending.add(id));schedule(1500);}
    finally{busy=false;if(!timer&&(full||pending.size))schedule();}
  }
  function schedule(delay=20){if(!timer&&!document.hidden)timer=setTimeout(flush,delay);}
  function request(ids=null){
    const detail=typeof initialAssetRoute==='function'?initialAssetRoute().asset:null;
    if(detail){if(ids!==null&&!ids.includes(detail))return;full=false;pending.clear();pending.add(detail);}
    else if(ids===null)full=true;else ids.forEach(id=>pending.add(id));schedule();
  }
  async function fallback(){clearTimeout(retry);if(connected||document.hidden)return;
    try{const change=await api('/api/changes'+(changeCursor?'?since='+encodeURIComponent(changeCursor):''));changeCursor=change.cursor;if(change.reset)request();else if(change.ids.length)request(change.ids);}catch{}
    if(!connected&&!document.hidden)retry=setTimeout(fallback,750);
  }
  function suspend(){source?.port.postMessage('close');source?.port.close();source=null;connected=false;clearTimeout(timer);timer=null;clearTimeout(retry);retry=null;}
  function connect(){
    if(source||document.hidden)return;
    if(typeof SharedWorker==='undefined'){fallback();return;}
    try{source=new SharedWorker('/live-worker.js',{name:'monkey-live-v1'});
      source.port.onmessage=event=>{const {type,change}=event.data;
        if(type==='open'){connected=true;clearTimeout(retry);request();}
        else if(type==='change')request(change.reset?null:change.ids);
        else{connected=false;fallback();}
      };source.port.start();source.onerror=()=>{suspend();fallback();};
    }catch{source=null;fallback();}
  }
  async function start(){
    if(started)return;started=true;
    // Detail pages only subscribe to their asset; the grid loads the catalog when opened.
    cursor=state.catalogCursor||null;
    connect();
  }
  window.addEventListener('workspace-write',event=>{if(started)request(event.detail?.ids||null);});
  window.addEventListener('focus',()=>{if(started){connect();request();}});
  window.addEventListener('visibilitychange',()=>{if(document.hidden)suspend();else if(started){connect();request();}});
  window.addEventListener('pagehide',suspend);
  window.addEventListener('pageshow',()=>{if(started){connect();request();}});
  window.addEventListener('load',start,{once:true});
  return {request,merge,jobsFor(asset){return [...jobs.values()].filter(j=>j.asset_id===asset).sort((a,b)=>b.created_at-a.created_at);}};
})();
