const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
test('approve selects the newest finished result, including visual warnings, before accepting it',async()=>{
  const calls=[],jobs=[{id:'failed-newest',asset_id:'a',status:'failed',created_at:5,image:'bad'},
    {id:'new',asset_id:'a',status:'ready',created_at:4,image:'new.png',candidate_sha256:'new-hash',quality:{passed:false}},
    {id:'old',asset_id:'a',status:'ready',created_at:1,image:'old.png'}];
  const context=vm.createContext({window:{dispatchEvent(){},addEventListener(){}},Event:class{},LiveAssets:{merge(){},request(){}},api:async(url,body)=>{
    calls.push({url,body});
    if(url.startsWith('/api/imagelab/jobs'))return {jobs};
    if(url.startsWith('/api/open'))return {revision:'current-revision',current_sha256:'old-hash'};
    if(url==='/api/variants/select')return {revision:'new-revision'};
    return {sha256:'new-hash'};
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../imagelab-ui.js'),'utf8'),context);
  await context.acceptLatestImageLabResult({id:'a'});
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c.url==='/api/variants/select').body)),{job_id:'new',revision:'current-revision'});
  assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c.url==='/api/imagelab/approve').body)),{id:'a',revision:'new-revision'});
  assert.equal(calls.at(-1).url,'/api/live-state?ids=a');
});
test('approval of an already current result is idempotent and does not overwrite it again',async()=>{
  const calls=[];
  const context=vm.createContext({window:{dispatchEvent(){},addEventListener(){}},Event:class{},LiveAssets:{merge(){},request(){}},api:async(url,body)=>{
    calls.push(url);if(url.startsWith('/api/imagelab/jobs'))return {jobs:[{id:'same',status:'applied',created_at:1,image:'image.png',candidate_sha256:'same-hash'}]};
    if(url.startsWith('/api/open'))return {revision:'r',current_sha256:'same-hash'};return {};
  }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../imagelab-ui.js'),'utf8'),context);
  await context.acceptLatestImageLabResult({id:'a'});
  assert.equal(calls.includes('/api/variants/select'),false);assert.equal(calls.includes('/api/imagelab/revoke'),false);
});
test('direct grid action sends the saved recipe and blocks double submission',async()=>{
  const requests=[];let finish;
  const recipe={prompt:'Specific dark wood contour',model:'chosen-model',style_id:'approved-reference',alpha_mode:'ai',preserve_alpha:true};
  const context=vm.createContext({window:{addEventListener(){},dispatchEvent(){}},Event:class{},localStorage:{getItem(){return JSON.stringify(recipe);}},api:async(url,body)=>{requests.push({url,body});await new Promise(resolve=>finish=resolve);return {id:'job',asset_id:'asset',status:'queued'};}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../imagelab-ui.js'),'utf8'),context);
  vm.runInContext('imageLabNotice=()=>{}',context);
  const button={};const first=context.enqueueImageLab({id:'asset',name:'sprite'},button);
  await context.enqueueImageLab({id:'asset',name:'sprite'},button);
  assert.equal(requests.length,1);assert.equal(button.disabled,true);
  assert.deepEqual(JSON.parse(JSON.stringify(requests[0].body)),{id:'asset',...recipe});
  finish();await first;assert.equal(button.disabled,false);
});
