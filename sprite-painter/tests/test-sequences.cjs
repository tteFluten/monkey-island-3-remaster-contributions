const test=require('node:test'),assert=require('node:assert/strict');
const tools=require('../sequence-tools.js');
const frames=[10,2,0].map(n=>({id:'walk'+n,group:'ship/walk_frame',category:'ship',name:'walk_frame_'+n,number:n,has_reference:true,revision:'r'+n}));
test('a filtered match selects the complete resource in numeric order, never another collection',()=>{
  const other={...frames[0],id:'other',category:'water'};
  const groups=tools.groups([...frames,other],[frames[0]]);
  assert.equal(groups.length,1);assert.equal(groups[0].matching,1);
  assert.deepEqual(groups[0].frames.map(f=>f.number),[0,2,10]);
});
test('explicit sequence generation includes approved frames and skips only active jobs or missing originals',()=>{
  const plan=tools.plan([...frames,frames[0],{id:'missing'}],{technique:'upscale',model:'Wonder 3.5 High + Bria'},{walk0:{}},new Map([['walk2',{status:'running'}]]));
  assert.deepEqual(plan.requests.map(r=>r.body.id),['walk10','walk0']);
  assert.deepEqual(plan.skipped,{busy:1,approved:0,original:1});
  for(const r of plan.requests){assert.equal(r.url,'/api/upscale/jobs');assert.equal(r.body.enhance_model,'Wonder 3.5 High + Bria');}
});
test('AI base and alpha recipes never substitute a different frame or drop revision protection',()=>{
  for(const f of frames){
    const p=tools.payload(f,{technique:'generate',model:'test',prompt:'Clean',base:'current',alpha:'none'});
    assert.equal(p.body.id,f.id);assert.equal(p.body.base_revision,f.revision);assert.equal(p.body.preserve_alpha,false);assert.equal(p.body.style_id,'');
    const a=tools.payload(f,{technique:'bria'});assert.equal(a.url,'/api/variants/extract-alpha');assert.equal(a.body.revision,f.revision);
  }
});
test('local operations have independent settings and frozen revisions',()=>{
  const f=frames[0],recipe={technique:'tint',trim:2,tint:.7,seams:true};
  assert.equal(tools.payload(f,recipe).body.trim_pixels,0);
  const p=tools.payload(f,{technique:'red-4'});f.revision='later';
  assert.equal(p.body.revision,'r10');assert.equal(p.body.outline,'red-4');assert.equal(p.body.protect_seams,false);
  const noRef=[{...f,has_reference:false}];
  assert.equal(tools.plan(noRef,recipe,{},new Map()).requests.length,0);
  assert.equal(tools.plan(noRef,{technique:'magenta'},{},new Map()).requests.length,1);
  assert.equal(tools.plan(frames,{technique:'upscale',skipApproved:true},{walk0:{}},new Map()).skipped.approved,1);
});
