const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

function fixture(){
  const frames=Array.from({length:8},(_,i)=>({id:String(i),name:`Asset ${i}`,category:'ship',has_reference:true,revision:`r${i}`}));
  const controls=new Map();
  function control(key){
    if(!controls.has(key))controls.set(key,{value:key==='[data-batch-scope]'?'all':'',checked:true,textContent:'',disabled:false,
      setAttribute(name,value){this[name]=value;},querySelector(selector){return control(key+' '+selector);}});
    return controls.get(key);
  }
  const panel={querySelector:control,classList:{toggle(){}}};
  const approvals={},jobs=new Map();
  const context=vm.createContext({state:{frames},imageLabApprovals:approvals,imageLabAssetJobs:jobs,window:{addEventListener(){}}});
  // Exercise the real private selection and target logic without exporting test hooks to the app.
  let code=fs.readFileSync(path.join(__dirname,'../asset-browser.js'),'utf8').split('async function openAssetBrowser()')[0];
  code=code.replace('return {open};',`return {pick,pickMany,clearSelection,batchTargets,actionCandidates,updateBatchControls,
    init(p,frames){panel=p;items=frames;},view(frames){items=frames;updateBatchControls();},
    busy(value){batchSending=value;updateBatchControls();},ids(){return [...picked];}};`);
  vm.runInContext(code,context);
  const grid=vm.runInContext('assetGrid',context);grid.init(panel,frames);
  return {grid,frames,control,approvals,jobs,ids:approval=>Array.from(grid.batchTargets(approval),f=>f.id)};
}

test('selected batch ignores an old all-assets scope and survives filtering',()=>{
  const f=fixture();f.grid.pick(1);f.grid.pick(3);
  assert.deepEqual(f.ids(true),['1','3']);assert.deepEqual(f.ids(),['1','3']);
  f.grid.view(f.frames.slice(4));
  assert.deepEqual(f.ids(true),['1','3']);
  assert.equal(f.control('[data-selection-count]').textContent,'2 seleccionados · 2 fuera del filtro');
  assert.equal(f.control('[data-batch-scope]').disabled,true);
  assert.equal(f.control('[data-approve-visible]').textContent,'Aprobar selección (2)');
});

test('Shift selects a range in displayed order, with a stable anchor',()=>{
  const f=fixture();f.grid.pick(4);f.grid.pick(1,true);
  assert.deepEqual(f.ids(true),['1','2','3','4']);
  f.grid.view([f.frames[7],f.frames[4],f.frames[0]]);f.grid.pick(2,true);
  assert.deepEqual(f.ids(true),['0','1','2','3','4']);
  f.grid.pick(1);assert.deepEqual(f.ids(true),['0','1','2','3']);
});

test('empty selection cannot silently fall back to all or filtered assets',()=>{
  const f=fixture();f.grid.pick(0);f.grid.clearSelection();
  assert.deepEqual(f.ids(true),[]);assert.deepEqual(f.ids(),[]);
  for(const selector of ['[data-batch]','[data-batch-approve]','[data-clean-auto]','[data-redo]','[data-approve-visible]'])assert.equal(f.control(selector).disabled,true);
  f.grid.clearSelection(true);assert.equal(f.ids(true).length,8);
  assert.equal(f.control('[data-batch-scope]').value,'filtered');
});

test('visible selection adds only supplied assets, keeps approvals and cleanup eligibility separate',()=>{
  const f=fixture();f.frames[1].edge_cleaned=true;f.approvals['2']={};
  f.jobs.set('3',{operation:'local-alpha',base_revision:'r3',status:'ready'});
  f.grid.pickMany(['0','1','2','3']);f.grid.pickMany(['0','4']);
  assert.deepEqual(f.ids(true),['0','1','3','4']);
  assert.deepEqual(f.ids(),['0','4']);
  assert.equal(f.control('[data-clean-auto]').textContent,'Limpiar bordes (2)');
  assert.equal(f.control('[data-approve-visible]').textContent,'Aprobar selección (4)');
  f.grid.busy(true);assert.equal(f.control('[data-clean-auto]').disabled,true);
  assert.equal(f.control('[data-approve-visible]').disabled,true);
});
