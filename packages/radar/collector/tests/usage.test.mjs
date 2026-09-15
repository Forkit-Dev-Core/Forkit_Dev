import test,{before,after,beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs/promises';
import {randomUUID,randomBytes} from 'node:crypto';
import {Pool} from 'pg';
import {createHandler} from '../collector.mjs';
import {COUNTERS,TOOLS,TOOL_FIELDS,parseUsage,aggregateUsage} from '../usage-contract.mjs';
import {canonical,shift,day} from '../contract.mjs';
import {cleanup,health} from '../maintenance.mjs';

const url=process.env.RADAR_TEST_DATABASE_URL;
if(!url)throw new Error('Select a disposable forkit_p11_* database.');
const pool=new Pool({connectionString:url,max:12,connectionTimeoutMillis:3000});
let now=new Date('2026-09-15T12:00:00Z'),server,base;
const identity=()=>({id:randomUUID(),token:randomBytes(32).toString('hex')});
function payload(sequence=1){
  const days=Array.from({length:29},(_,i)=>({date:day(shift(new Date('2026-09-15T00:00:00Z'),i-28)),...Object.fromEntries(COUNTERS.map(k=>[k,0])),detected_tools:[],session_tools:Object.fromEntries(TOOL_FIELDS.map(k=>[k,0]))}));
  for(const i of [26,27])Object.assign(days[i],{scans:1,successful_scans:1,detection_observations:3,receipts:1,during_changes:2,between_changes:1,reconstructable_changes:2,passport_versions_created:1,detected_tools:['codex'],session_tools:{codex:1,claude_code:0,cursor:0,other:0}});
  return {schema_version:'2.0',kind:'forkit_usage_contribution',policy:'usage-v2',audience:'validation',sequence,generated_on:'2026-09-15',collection_complete:true,days,passport_windows:days.map((d,i)=>({end_exclusive:d.date,distinct_passports:i>=27?1:0}))};
}
async function serve(options={}){
  if(server)await new Promise(r=>server.close(r));
  server=http.createServer(createHandler({pool,secret:Buffer.alloc(32,17),protocol:'usage',enabled:true,allowLocalHttp:true,clock:()=>now,...options}));
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  base='http://127.0.0.1:'+server.address().port+'/api/v1/radar';
}
async function submit(who,p=payload(),method='PUT',raw){
  const body=raw??(method==='DELETE'?'':canonical(p));
  return fetch(base+'/installations/'+who.id,{method,body,headers:{Authorization:'Bearer '+who.token,'Content-Type':'application/json','Content-Length':String(Buffer.byteLength(body))}});
}
async function metrics(){const r=await fetch(base+'/usage');return {status:r.status,value:await r.json()};}
function engagementPayload(){
  const p=payload();p.schema_version='3.0';p.policy='usage-v3';
  p.days.forEach((d,i)=>Object.assign(d,{viewed:i>=26&&i<=27?1:0,history_viewed:i===27?1:0,card_exports:i===27?1:0}));
  return p;
}
before(async()=>{
  assert.match((await pool.query('SELECT current_database() AS name')).rows[0].name,/^forkit_p11_/);
  await pool.query(await fs.readFile(new URL('../schema.sql',import.meta.url),'utf8'));
  await pool.query(await fs.readFile(new URL('../usage-schema.sql',import.meta.url),'utf8'));
});
beforeEach(async()=>{now=new Date('2026-09-15T12:00:00Z');await pool.query('TRUNCATE radar_metrics.installations,radar_metrics.rate_limits');await serve();});
after(async()=>{if(server)await new Promise(r=>server.close(r));await pool.end();});

test('strict private-field, date, count, duplicate-key and tool boundaries',()=>{
  const p=payload();assert.deepEqual(parseUsage(Buffer.from(canonical(p)),now),p);
  for(const change of [p=>p.passport_id='SECRET',p=>p.days[27].source='SECRET',p=>p.sequence=true,p=>p.days[27].detected_tools=['secret-tool'],p=>p.days[27].detected_tools=['codex','codex'],p=>p.days[27].scans=-1,p=>p.days[27].receipts=3,p=>p.passport_windows[28].distinct_passports=9,p=>p.generated_on='2026-09-16']){
    const value=structuredClone(p);change(value);assert.throws(()=>parseUsage(Buffer.from(canonical(value)),now));
  }
  assert.throws(()=>parseUsage(Buffer.from('{"sequence":1,'+canonical(p).slice(1)),now));
  assert.throws(()=>parseUsage(Buffer.from(' '+canonical(p)),now));
});
test('five profile suppression and exact 7/28 complete UTC windows',async()=>{
  assert.equal((await metrics()).value.status,'empty');
  for(let i=0;i<4;i++)assert.equal((await submit(identity())).status,200);
  assert.equal((await metrics()).value.metrics,null);
  await submit(identity());const m=(await metrics()).value;
  assert.equal(m.start_7_days,'2026-09-08');assert.equal(m.start_28_days,'2026-08-18');assert.equal(m.end_exclusive,'2026-09-15');
  assert.equal(m.metrics.participating_profiles_28_days,5);assert.equal(m.metrics.receipts,10);assert.equal(m.metrics.receipts_7_days,10);
  assert.equal(m.metrics.weekly_active_profiles,5);assert.equal(m.metrics.weekly_repeat_profiles,5);
  assert.equal(m.metrics.repeat_check_rate_basis_points,10000);
  assert.equal(m.metrics.meaningful_changes,30);assert.equal(m.metrics.reconstructable_change_rate_basis_points,6666);
  assert.equal(m.metrics.weekly_active_passports,5);assert.equal(m.metrics.detected_tool_profiles_28_days.codex,5);
  assert.equal(m.metrics.total_installs,null);
});
test('tool presence cannot be mistaken for selected session tool or unique agents',()=>{
  const p=payload();for(const d of p.days)if(d.receipts){d.session_tools={codex:0,claude_code:0,cursor:1,other:0};}
  const m=aggregateUsage(Array.from({length:5},()=>({payload:p})),now).metrics;
  assert.equal(m.detected_tool_profiles_28_days.codex,5);assert.equal(m.detected_tool_profiles_28_days.cursor,0);
  assert.equal(m.session_tool_receipts_28_days.cursor,10);assert.equal(m.detection_observations,30);
});
test('small tool cohorts are suppressed even with five total contributors',()=>{
  const rows=Array.from({length:5},()=>({payload:payload()}));rows[0].payload.days[27].detected_tools=['codex','cursor'];
  assert.equal(aggregateUsage(rows,now).metrics.detected_tool_profiles_28_days.cursor,null);
});
test('small positive Passport subgroups stay suppressed despite complete activity coverage',()=>{
  const rows=Array.from({length:5},()=>({payload:payload()}));
  for(const row of rows.slice(1))for(const window of row.payload.passport_windows)window.distinct_passports=0;
  assert.equal(aggregateUsage(rows,now).metrics.weekly_active_passports,null);
  for(const window of rows[0].payload.passport_windows)window.distinct_passports=0;
  assert.equal(aggregateUsage(rows,now).metrics.weekly_active_passports,0);
});
test('today activity is excluded and stale Passport coverage is explicit',()=>{
  const p=payload();Object.assign(p.days[28],{receipts:100,session_tools:{codex:100,claude_code:0,cursor:0,other:0}});
  const rows=Array.from({length:5},()=>({payload:p}));
  assert.equal(aggregateUsage(rows,now).metrics.receipts,10);
  const next=aggregateUsage(rows,new Date('2026-09-16T12:00:00Z')).metrics;
  assert.equal(next.receipts,510);assert.equal(next.weekly_active_passports,null);assert.equal(next.current_snapshot_profiles,0);
});
test('partial history or collection makes reconstruction rate unavailable',()=>{
  const p=payload();p.collection_complete=false;
  const rows=Array.from({length:5},()=>({payload:p}));
  assert.equal(aggregateUsage(rows,now).metrics.reconstructable_change_rate_basis_points,null);
  assert.equal(aggregateUsage(rows,now).metrics.repeat_check_rate_basis_points,null);
});
test('validation profiles cannot enter community collection or production aggregates',async()=>{
  await serve({environment:'production',tlsTerminated:true});
  assert.equal((await submit(identity())).status,400);
  const rows=Array.from({length:5},()=>({payload:payload()}));
  assert.equal(aggregateUsage(rows,now,{environment:'production'}).status,'empty');
});
test('retry is idempotent, sequence replacement corrects counts, credentials bind profile',async()=>{
  const who=identity();await submit(who);
  assert.equal((await (await submit(who)).json()).status,'unchanged');
  const p=payload(2);p.days[27].detection_observations=1;
  assert.equal((await submit(who,p)).status,200);
  assert.equal((await submit(who)).status,409);
  assert.equal((await submit({...who,token:'a'.repeat(64)},payload(3))).status,401);
  const rows=(await pool.query('SELECT * FROM radar_metrics.installations')).rows;
  assert.equal(rows.length,1);assert.equal(rows[0].payload.days[27].detection_observations,1);
  assert.ok(!JSON.stringify(rows).includes(who.id)&&!JSON.stringify(rows).includes(who.token));
});
test('withdrawal before first PUT and repeated withdrawal reject delayed reports',async()=>{
  const who=identity();assert.equal((await submit(who,null,'DELETE')).status,204);
  assert.equal((await submit(who)).status,410);
  assert.equal((await submit(who,null,'DELETE')).status,204);
});
test('database serializes concurrent profile creation at capacity',async()=>{
  await serve({maxProfiles:5});
  const replies=await Promise.all(Array.from({length:10},()=>submit(identity())));
  assert.equal(replies.filter(r=>r.status===200).length,5);
  assert.equal(replies.filter(r=>r.status===503).length,5);
});
test('idle cleanup expires bodies but preserves replay rejection without public reads',async()=>{
  const who=identity();await submit(who);assert.equal(await health(pool),true);
  await cleanup(pool,new Date('2026-10-21T12:00:00Z'));
  const row=(await pool.query('SELECT payload,sequence FROM radar_metrics.installations')).rows[0];
  assert.equal(row.payload,null);assert.equal(Number(row.sequence),1);
  assert.equal((await submit(who)).status,409);
});
test('disabled collector fails closed without creating adoption rows',async()=>{
  await serve({enabled:false});assert.equal((await submit(identity())).status,503);
  assert.equal(Number((await pool.query('SELECT COUNT(*) AS n FROM radar_metrics.installations')).rows[0].n),0);
});

test('weekly receipts exclude older activity and suppress small contributors',()=>{
  const rows=Array.from({length:5},()=>({payload:payload()}));
  for(const row of rows){
    row.payload.days[10].receipts=20;row.payload.days[10].session_tools.codex=20;
  }
  const m=aggregateUsage(rows,now).metrics;
  assert.equal(m.receipts,110);assert.equal(m.receipts_7_days,10);
  for(const row of rows.slice(1))for(const i of [26,27]){
    row.payload.days[i].receipts=0;row.payload.days[i].session_tools.codex=0;
    row.payload.days[i].during_changes=0;row.payload.days[i].between_changes=0;row.payload.days[i].reconstructable_changes=0;
    row.payload.days[i].passport_versions_created=0;
    for(const w of row.payload.passport_windows)w.distinct_passports=0;
  }
  assert.equal(aggregateUsage(rows,now).metrics.receipts_7_days,null);
});

test('new consent protocol round-trips over HTTP and adds daily/viewing metrics',async()=>{
  for(let i=0;i<5;i++){
    const reply=await submit(identity(),engagementPayload());assert.equal(reply.status,200);
    assert.equal((await reply.json()).schema_version,'3.0');
  }
  const m=(await metrics()).value.metrics;
  assert.equal(m.receipts_yesterday,5);assert.equal(m.during_changes_yesterday,10);
  assert.equal(m.viewing_profiles_7_days,5);assert.equal(m.repeat_viewing_profiles_7_days,5);
  assert.equal(m.repeat_view_rate_basis_points,10000);assert.equal(m.card_exports_7_days,5);
  assert.equal(m.daily_date,'2026-09-14');assert.equal(m.total_installs,null);
});

test('legacy activity never becomes engagement and missing/stale coverage stays unknown',()=>{
  const legacy=Array.from({length:5},()=>({payload:payload()}));
  const m=aggregateUsage(legacy,now).metrics;
  assert.equal(m.viewing_profiles_7_days,null);assert.equal(m.repeat_view_rate_basis_points,null);
  const rows=Array.from({length:5},()=>({payload:engagementPayload()}));
  assert.equal(aggregateUsage(rows,new Date('2026-09-16T12:00:00Z')).metrics.receipts_yesterday,null);
  rows[0].payload.days[26].viewed=0;
  assert.equal(aggregateUsage(rows,now).metrics.repeat_view_rate_basis_points,null);
  rows[0].payload.collection_complete=false;
  assert.equal(aggregateUsage(rows,now).metrics.repeat_view_rate_basis_points,null);
});

test('v3 private fields, incompatible consent and fabricated daily flags are rejected',()=>{
  for(const change of [p=>p.policy='usage-v2',p=>p.days[27].viewed=2,p=>p.days[27].viewed=true,p=>p.days[27].viewed=0,p=>p.days[27].url='private',p=>p.days[27].card_exports=-1]){
    const p=engagementPayload();change(p);assert.throws(()=>parseUsage(Buffer.from(canonical(p)),now));
  }
});
