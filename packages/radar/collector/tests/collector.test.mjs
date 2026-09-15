import test,{before,after,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import {randomUUID,randomBytes} from 'node:crypto';
import {Pool} from 'pg';
import express from 'express';
import {createHandler,aggregate} from '../collector.mjs';
import {canonical,parse,validate,COUNT_FIELDS} from '../contract.mjs';

const url=process.env.RADAR_TEST_DATABASE_URL;
if(!url)throw new Error('RADAR_TEST_DATABASE_URL must select a disposable forkit_p11_* database.');
const pool=new Pool({connectionString:url,max:12,connectionTimeoutMillis:5000});
const initial=new Date('2026-09-16T12:00:00Z');
let now,server,base;
const identity=()=>({id:randomUUID(),token:randomBytes(32).toString('hex')});
function payload(sequence=1){
  const weeks=['2026-08-24','2026-08-31','2026-09-07','2026-09-14'].map(start=>({start,...Object.fromEntries(COUNT_FIELDS.map(k=>[k,0]))}));
  Object.assign(weeks[3],{active_days:2,scans:2,successful_scans:1,receipts:2,meaningful_changes:3,during_changes:2,between_changes:1,reconstructable_changes:2,active_passports:1,passport_versions_created:1,partial_receipts:1});
  return {schema_version:'1.0',kind:'forkit_usage_contribution',policy:'session-metrics-v1',sequence,generated_on:'2026-09-16',weeks,latest_discovery:{observed_on:'2026-09-16',models:3,agents:2,mcp_servers:1,applications_and_processes:2,partial:true}};
}
async function serve(options={}){
  if(server)await new Promise(resolve=>server.close(resolve));
  server=http.createServer({maxHeaderSize:8192},createHandler({pool,secret:Buffer.alloc(32,11),enabled:true,environment:'validation',clock:()=>now,allowLocalHttp:true,...options}));
  server.requestTimeout=10000;server.headersTimeout=10000;
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base='http://127.0.0.1:'+server.address().port+'/api/v1/radar';
}
async function submit(who,value=payload(),{method='PUT',headers={},raw}={}){
  const body=raw??(method==='DELETE'?'':canonical(value));
  return fetch(base+'/surfaces/'+who.id,{method,body,headers:{Authorization:'Bearer '+who.token,'Content-Type':'application/json','Content-Length':String(Buffer.byteLength(body)),...headers}});
}
const metrics=async()=>{const r=await fetch(base+'/metrics');return {status:r.status,value:await r.json()};};
before(async()=>{
  const database=(await pool.query('SELECT current_database() AS name')).rows[0].name;
  assert.match(database,/^forkit_p11_/,'Only a disposable task database may be used.');
  await pool.query(await fs.readFile(new URL('../schema.sql',import.meta.url),'utf8'));
});
beforeEach(async()=>{
  now=new Date(initial);
  await pool.query('TRUNCATE radar_metrics.surfaces,radar_metrics.rate_limits');
  await serve();
});
after(async()=>{
  if(server)await new Promise(resolve=>server.close(resolve));
  await pool.end();
});

test('disabled intake does not touch the selected database',async()=>{
  await serve({enabled:false});
  assert.equal((await submit(identity())).status,503);
  assert.equal((await metrics()).status,503);
  assert.equal(Number((await pool.query('SELECT count(*) AS n FROM radar_metrics.surfaces')).rows[0].n),0);
});
test('strict canonical contract rejects duplicates, unknown/private fields and contradictory counts',()=>{
  const original=payload();
  assert.deepEqual(parse(Buffer.from(canonical(original)),now),original);
  for(const mutate of [
    p=>p.passport_id='PRIVATE',p=>p.sequence=true,p=>p.weeks[3].receipts=-1,
    p=>p.weeks[3].receipts=1.5,p=>p.weeks[3].reconstructable_changes=4,
    p=>p.weeks[3].active_days=4,p=>p.weeks[0].start='2026-02-30',
    p=>p.latest_discovery.url='https://PRIVATE',p=>p.generated_on='2026-09-17',
    p=>p.generated_on='2026-09-01',p=>p.latest_discovery.models=100000001,
    p=>p.weeks[3].scans=0,p=>p.weeks[3].active_passports=99
  ]){const p=structuredClone(original);mutate(p);assert.throws(()=>validate(p,now));}
  assert.throws(()=>parse(Buffer.from(' '+canonical(original)),now));
  assert.throws(()=>parse(Buffer.from('{"sequence":1,'+canonical(original).slice(1)),now));
  assert.throws(()=>parse(Buffer.alloc(32769),now));
});
test('latest snapshot replaces counts and identical retries cannot inflate or refresh activity',async()=>{
  const who=identity(),p=payload();
  assert.equal((await submit(who,p)).status,200);
  const first=(await pool.query('SELECT updated_at FROM radar_metrics.surfaces')).rows[0].updated_at;
  now=new Date('2026-09-17T12:00:00Z');
  const r=await submit(who,p);assert.equal((await r.json()).status,'unchanged');
  assert.equal((await pool.query('SELECT updated_at FROM radar_metrics.surfaces')).rows[0].updated_at.toISOString(),first.toISOString());
  p.sequence=2;p.weeks[3].passport_versions_created=7;
  assert.equal((await submit(who,p)).status,200);
  assert.equal(Number((await pool.query('SELECT count(*) AS n FROM radar_metrics.surfaces')).rows[0].n),1);
  assert.equal((await pool.query('SELECT payload FROM radar_metrics.surfaces')).rows[0].payload.weeks[3].passport_versions_created,7);
});
test('wrong credentials, sequence rollback and same-sequence different data fail',async()=>{
  const who=identity();await submit(who,payload(2));
  assert.equal((await submit({...who,token:'a'.repeat(64)},payload(3))).status,401);
  assert.equal((await submit(who,payload(1))).status,409);
  const changed=payload(2);changed.weeks[3].scans++;
  assert.equal((await submit(who,changed)).status,409);
});
test('withdrawal is authenticated, idempotent and rejects a delayed initial upload',async()=>{
  const first=identity();await submit(first);
  assert.equal((await submit({...first,token:'c'.repeat(64)},null,{method:'DELETE'})).status,401);
  assert.equal((await submit(first,null,{method:'DELETE'})).status,204);
  assert.equal((await submit(first,null,{method:'DELETE'})).status,204);
  assert.equal((await submit(first,payload(2))).status,410);
  const fresh=identity();
  assert.equal((await submit(fresh,null,{method:'DELETE'})).status,204);
  assert.equal((await submit(fresh)).status,410);
  const rows=(await pool.query('SELECT payload,withdrawn FROM radar_metrics.surfaces')).rows;
  assert.equal(rows.length,2);assert.ok(rows.every(r=>r.payload===null&&r.withdrawn));
});
test('public metrics require five profiles and use correct aggregate denominators',async()=>{
  assert.equal((await metrics()).value.status,'empty');
  const people=Array.from({length:5},identity);
  for(let i=0;i<4;i++)await submit(people[i]);
  let m=(await metrics()).value;assert.equal(m.status,'collecting');assert.equal(m.metrics,null);
  await submit(people[4]);
  m=(await metrics()).value;
  assert.equal(m.environment,'validation');assert.equal(m.status,'available');
  assert.equal(m.metrics.reporting_profiles,5);assert.equal(m.metrics.receipts,10);
  assert.equal(m.metrics.meaningful_changes,15);assert.equal(m.metrics.reconstructable_changes,10);
  assert.equal(m.metrics.reconstructable_change_rate_basis_points,6666);
  assert.equal(m.metrics.repeat_check_rate_basis_points,10000);
  assert.equal(m.metrics.weekly_active_passports,5);
  assert.equal(m.metrics.latest_discovery.models,15);assert.equal(m.metrics.latest_discovery.agents,10);
  assert.equal(m.metrics.total_installs,null);
  const raw=JSON.stringify(m);
  for(const person of people){assert.ok(!raw.includes(person.id));assert.ok(!raw.includes(person.token));}
  await submit(people[0],null,{method:'DELETE'});
  assert.equal((await metrics()).value.status,'collecting');
});
test('incomplete retained counts make reconstruction percentage unavailable',()=>{
  const p=payload();p.weeks[3].incomplete_history_receipts=1;
  const result=aggregate(Array.from({length:5},()=>({payload:p})),now);
  assert.equal(result.metrics.reconstructable_change_rate_basis_points,null);
  assert.equal(result.metrics.meaningful_changes,15);
});
test('zero denominators remain null rather than 100 percent',()=>{
  const p=payload();p.latest_discovery=null;
  for(const w of p.weeks)for(const k of COUNT_FIELDS)w[k]=0;
  const r=aggregate(Array.from({length:5},()=>({payload:p})),now);
  assert.equal(r.metrics.reconstructable_change_rate_basis_points,null);
  assert.equal(r.metrics.repeat_check_rate_basis_points,null);
});
test('stale profiles leave totals and old contribution bodies are removed',async()=>{
  const who=identity();await submit(who);
  now=new Date('2026-09-24T12:00:00Z');
  assert.equal((await metrics()).value.metrics.reporting_profiles,0);
  now=new Date('2026-10-19T12:00:00Z');
  assert.equal((await metrics()).value.status,'empty');
  const row=(await pool.query('SELECT payload,credential_hash,sequence FROM radar_metrics.surfaces')).rows[0];
  assert.equal(row.payload,null);assert.equal(Number(row.sequence),1);
  assert.match(row.credential_hash,/^[a-f0-9]{64}$/);
});
test('HTTP input boundaries refuse unsafe transport, browser writes and noncanonical bodies',async()=>{
  const who=identity();
  assert.equal((await submit(who,payload(),{headers:{Origin:'https://foreign.example'}})).status,400);
  assert.equal((await submit(who,payload(),{headers:{Authorization:'not a token'}})).status,401);
  assert.equal((await submit(who,payload(),{headers:{'Content-Type':'text/plain'}})).status,415);
  assert.equal((await submit(who,payload(),{raw:' '+canonical(payload())})).status,400);
  assert.equal((await submit(who,payload(),{raw:'x'.repeat(32769)})).status,413);
  await serve({allowLocalHttp:false});
  assert.equal((await submit(who)).status,426);
});
test('forwarded headers cannot evade the shared address limit',async()=>{
  await serve({perAddressPerHour:2});
  assert.equal((await submit(identity(),payload(),{headers:{'X-Forwarded-For':'1.1.1.1'}})).status,200);
  assert.equal((await submit(identity(),payload(),{headers:{'X-Forwarded-For':'2.2.2.2'}})).status,200);
  assert.equal((await submit(identity(),payload(),{headers:{'X-Forwarded-For':'3.3.3.3'}})).status,429);
  const raw=JSON.stringify((await pool.query('SELECT * FROM radar_metrics.rate_limits')).rows);
  assert.ok(!raw.includes('127.0.0.1')&&!raw.includes('1.1.1.1'));
});
test('simultaneous profile registration respects database-wide capacity',async()=>{
  await serve({maxProfiles:5});
  const results=await Promise.all(Array.from({length:10},()=>submit(identity())));
  assert.equal(results.filter(r=>r.status===200).length,5);
  assert.equal(results.filter(r=>r.status===503).length,5);
  assert.equal(Number((await pool.query('SELECT count(*) AS n FROM radar_metrics.surfaces')).rows[0].n),5);
});
test('concurrent sequences retain the newest accepted contribution',async()=>{
  const who=identity();await submit(who);
  const results=await Promise.all(Array.from({length:12},(_,i)=>submit(who,payload(i+2))));
  assert.ok(results.every(r=>[200,409].includes(r.status)));
  const rows=(await pool.query('SELECT sequence FROM radar_metrics.surfaces')).rows;
  assert.equal(rows.length,1);assert.equal(Number(rows[0].sequence),13);
});
test('a failed statement rolls back a newly reserved profile',async()=>{
  await pool.query("ALTER TABLE radar_metrics.surfaces ADD CONSTRAINT fail_fixture CHECK(sequence=0)");
  try{
    assert.equal((await submit(identity())).status,503);
    assert.equal(Number((await pool.query('SELECT count(*) AS n FROM radar_metrics.surfaces')).rows[0].n),0);
  }finally{await pool.query('ALTER TABLE radar_metrics.surfaces DROP CONSTRAINT fail_fixture');}
});
test('corrupt database payload fails closed rather than publishing partial totals',async()=>{
  const who=identity();await submit(who);
  await pool.query("UPDATE radar_metrics.surfaces SET payload=jsonb_set(payload,'{weeks,3,receipts}','true')");
  assert.equal((await metrics()).status,503);
});
test('database and response never retain raw public handles or update tokens',async()=>{
  const who=identity();await submit(who);
  const stored=JSON.stringify((await pool.query('SELECT * FROM radar_metrics.surfaces')).rows);
  assert.ok(!stored.includes(who.id));assert.ok(!stored.includes(who.token));
  assert.ok(!stored.includes('PRIVATE')&&!stored.includes('127.0.0.1'));
});

test('Express mount before the existing body parser preserves unrelated routes',async()=>{
  await new Promise(resolve=>server.close(resolve));
  const app=express();
  app.use('/api/v1/radar',createHandler({pool,secret:Buffer.alloc(32,11),enabled:true,clock:()=>now,allowLocalHttp:true}));
  app.use(express.json());
  app.post('/other', (req,res)=>res.json({unchanged:req.body.hello==='world'}));
  server=http.createServer(app);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  base='http://127.0.0.1:'+server.address().port+'/api/v1/radar';
  assert.equal((await submit(identity())).status,200);
  assert.equal((await metrics()).value.status,'collecting');
  const other=await fetch('http://127.0.0.1:'+server.address().port+'/other',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"hello":"world"}'});
  assert.deepEqual(await other.json(),{unchanged:true});
});

test('unselected discovery categories remain unknown in the aggregate',()=>{
  const p=payload();p.latest_discovery.models=null;p.latest_discovery.agents=null;
  const result=aggregate(Array.from({length:5},()=>({payload:p})),now);
  assert.equal(result.metrics.latest_discovery.models,null);
  assert.equal(result.metrics.discovery_profile_coverage.models,0);
  assert.equal(result.metrics.latest_discovery.mcp_servers,5);
  assert.equal(result.metrics.discovery_profile_coverage.mcp_servers,5);
});
