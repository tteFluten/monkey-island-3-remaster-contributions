const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
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
