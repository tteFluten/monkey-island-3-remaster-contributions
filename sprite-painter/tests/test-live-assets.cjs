const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('live patches preserve catalog identity, invalidate only changed images, and clear revoked approvals',()=>{
  const a={id:'a',revision:'old',thumbnail_version:'old'},b={id:'b',revision:null,thumbnail_version:'b'};
  const cache=new Map([['a','old bitmap'],['b','keep bitmap']]),events=[],badge={};
  const context=vm.createContext({state:{frames:[a,b],groups:[[a,b]],info:{revision:'unsaved-base'},version:2,saved:1},cache,
    imageLabApprovals:{a:{sha256:'old'},b:{sha256:'keep'}},document:{querySelectorAll:()=>[badge]},
    window:{addEventListener(){},dispatchEvent(event){events.push(event);}},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}}});
  vm.runInContext('function syncImageLabAssets(jobs,approvals){imageLabApprovals=approvals;}',context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../live-assets.js'),'utf8'),context);
  const live=vm.runInContext('LiveAssets',context);
  live.merge({ids:['a'],full:false,frames:[{id:'a',revision:'new',thumbnail_version:'new'}],approvals:{a:null},jobs:[{id:'j',asset_id:'a',status:'ready',created_at:1}]});
  assert.equal(context.state.frames[0],a);assert.equal(a.revision,'new');
  assert.equal(cache.has('a'),false);assert.equal(cache.get('b'),'keep bitmap');
  assert.equal(context.imageLabApprovals.a,undefined);assert.ok(context.imageLabApprovals.b);
  assert.equal(context.state.info.revision,'unsaved-base');assert.equal(context.state.version,2);
  assert.equal(badge.textContent,'Cola de trabajos · 0 pendientes · 1 para revisar');
  assert.deepEqual(Array.from(events.at(-1).detail.changed),['a']);
  cache.set('a','new bitmap');
  live.merge({ids:['a'],full:false,frames:[{id:'a',revision:'new',thumbnail_version:'new'}],approvals:{a:{sha256:'approved'}},jobs:[{id:'j',asset_id:'a',status:'applied',created_at:1}]});
  assert.equal(cache.get('a'),'new bitmap');assert.equal(badge.textContent,'Cola de trabajos · 0 pendientes · 0 para revisar');
  assert.deepEqual(Array.from(events.at(-1).detail.changed),[]);
});
