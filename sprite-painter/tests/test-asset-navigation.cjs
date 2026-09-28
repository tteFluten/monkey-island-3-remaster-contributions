const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function fixture(){
  const session=new Map(),shared=new Map(),controls=new Map();
  const storage=map=>({getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v)});
  const q=key=>{if(!controls.has(key))controls.set(key,{value:''});return controls.get(key);};
  const context=vm.createContext({URLSearchParams,location:{search:'?browser=return-point'},sessionStorage:storage(session),localStorage:storage(shared),window:{addEventListener(){}}});
  let code=fs.readFileSync(path.join(__dirname,'../asset-browser.js'),'utf8').split('async function openAssetBrowser()')[0];
  code=code.replace('return {open,hide};',`return {savedView,rememberView,snapshotView,init(p){panel=p;search=p.querySelector('[data-search]');collection=p.querySelector('[data-collection]');filter=p.querySelector('[data-filter]');order=p.querySelector('[data-order]');items=[{id:'water'}];selected=0;picked.add('water');selectionMode=true;panX=-127;panY=-640;scale=1.18;cols=6;viewReady=true;}};`);
  vm.runInContext(code,context);const grid=vm.runInContext('assetGrid',context);grid.init({querySelector:q});
  q('[data-search]').value='0051';q('[data-collection]').value='Agua';
  return {grid,session,shared,q};
}
test('grid snapshot preserves search, collection, selection, pan and zoom across a detail tab',()=>{
  const f=fixture();f.grid.rememberView();const snapshot=f.session.get('monkey-assets-view');
  f.session.clear();f.shared.set('monkey-assets-return:return-point',snapshot);
  const restored=f.grid.savedView();assert.equal(restored.filters[0],'0051');assert.equal(restored.filters[1],'Agua');
  assert.equal(restored.panX,-127);assert.equal(restored.panY,-640);assert.equal(restored.scale,1.18);
  assert.deepEqual(Array.from(restored.picked),['water']);assert.equal(restored.selectionMode,true);assert.equal(restored.focused,'water');
});
test('reload uses this tab latest filters, including All collections, instead of a stale return snapshot',()=>{
  const f=fixture();f.grid.rememberView();f.shared.set('monkey-assets-return:return-point',f.session.get('monkey-assets-view'));
  f.q('[data-collection]').value='';f.q('[data-search]').value='changed';f.grid.rememberView();
  const restored=f.grid.savedView();assert.equal(restored.filters[1],'');assert.equal(restored.filters[0],'changed');
  f.session.set('monkey-assets-view','broken');assert.equal(f.grid.savedView(),null);
});
