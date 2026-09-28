const test=require('node:test'),assert=require('node:assert/strict');
const tools=require('../sequence-tools.js');
const frames=[10,2,0].map(n=>({id:'walk'+n,group:'ship/walk_frame',category:'ship',name:'walk_frame_'+n,number:n,has_reference:true,revision:'r'+n}));
test('sea selection includes animated water frames only',()=>{
  const frames=['LFLF_0011_AKOS_0051_frame_0','LFLF_0011_AKOS_0054_frame_87','LFLF_0009_AKOS_0030_frame_0','0011_background','0011_object_0000'].map(name=>({name}));
  assert.deepEqual(tools.waterFrames(frames),frames.slice(0,2));
});
test('batch application uses newest results and protects edited assets and warning results',()=>{
  const selected=['a','b','c','d','e','f','g','h'].map(id=>({id,revision:'current'}));
  const job=(asset_id,status='ready',extra={})=>({id:asset_id+'-job',asset_id,status,created_at:1,base_revision:'current',image:'test.png',...extra});
  const jobs=[job('a'),job('b'),job('b','running',{created_at:2}),job('c','ready',{base_revision:'old'}),job('d','ready',{quality:{passed:false}}),job('e','applied'),job('f','ready',{image:null}),job('g','failed')];
  const rows=tools.results(selected,jobs);
  assert.deepEqual(rows.filter(r=>!r.reason).map(r=>r.frame.id),['a']);
  assert.equal(rows[1].reason,'En proceso');assert.equal(rows[2].reason,'Cambió la versión en uso');
  assert.deepEqual(tools.results(selected,jobs,true).filter(r=>!r.reason).map(r=>r.frame.id),['a','d']);
  assert.equal(rows[7].reason,'Sin generación');
});
test('unedited catalog frames use the generation revision; legacy results without it are excluded',()=>{
  const frames=[{id:'base',revision:null},{id:'legacy',revision:null}];
  const jobs=frames.map(f=>({asset_id:f.id,status:'ready',image:'test.png',created_at:1,base_revision:f.id==='base'?'original-hash':undefined}));
  const rows=tools.results(frames,jobs);
  assert.equal(rows[0].reason,'');assert.equal(rows[0].frame.revision??rows[0].job.base_revision,'original-hash');
  assert.equal(rows[1].reason,'Sin revisión de origen');
});
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
