/**
 * Aggregate collector for the existing Express/PostgreSQL architecture.
 * Mount before any JSON/body parser; this handler verifies the exact raw bytes.
 * No Core identity, account, Passport, AI Footprints or customer tables are used.
 */
import {createHash,createHmac,timingSafeEqual} from 'node:crypto';
import {MAX_WIRE,COUNT_FIELDS,parse,validate,canonical,date,day,shift,monday} from './contract.mjs';

import {parseUsage,aggregateUsage} from './usage-contract.mjs';

const BASE='/api/v1/radar';
const SURFACE=/^\/api\/v1\/radar\/surfaces\/([a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})$/;
const TOKEN=/^Bearer ([a-f0-9]{64})$/;
class Failure extends Error { constructor(status,code){super(code);this.status=status;this.code=code;} }
const reject=(status,code)=>{throw new Failure(status,code);};
const same=(a,b)=>typeof a==='string' && a.length===b.length && timingSafeEqual(Buffer.from(a),Buffer.from(b));
const loopback=address=>['127.0.0.1','::1','::ffff:127.0.0.1'].includes(address);

async function transaction(pool,work) {
  const db=await pool.connect();
  try {
    await db.query('BEGIN');
    await db.query("SET LOCAL statement_timeout='5s'");
    await db.query("SET LOCAL lock_timeout='2s'");
    const result=await work(db);
    await db.query('COMMIT');
    return result;
  } catch(error) {
    await db.query('ROLLBACK').catch(()=>{});
    throw error;
  } finally { db.release(); }
}
function read(req) {
  return new Promise((resolve,rejectRead)=>{
    let size=0, settled=false;
    const chunks=[];
    const fail=error=>{if(!settled){settled=true;rejectRead(error);}};
    req.on('data',chunk=>{
      size+=chunk.length;
      if(size>MAX_WIRE){req.pause();fail(new Failure(413,'payload_limit'));return;}
      if(!settled)chunks.push(chunk);
    });
    req.once('end',()=>{if(!settled){settled=true;resolve(Buffer.concat(chunks));}});
    req.once('error',()=>fail(new Failure(400,'request_failed')));
    req.once('aborted',()=>fail(new Failure(400,'request_aborted')));
    req.setTimeout(8000,()=>{req.pause();fail(new Failure(408,'request_timeout'));});
  });
}
function response(res,status,payload) {
  res.statusCode=status;
  res.setHeader('Cache-Control','no-store');
  res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Referrer-Policy','no-referrer');
  if(payload!==undefined){res.setHeader('Content-Type','application/json');res.end(canonical(payload));}
  else res.end();
}
export function aggregate(rows,now,{environment='validation',minimumProfiles=5}={}) {
  const today=date(day(now)), first=shift(monday(today),-21), current=day(monday(today));
  const accepted=rows.map(r=>validate(r.payload,now));
  const basic={
    schema_version:'1.0',kind:'forkit_public_metrics',policy:'session-metrics-v1',
    environment,generated_at:now.toISOString(),window_start:day(first),window_end:day(today),
    week_start:current,minimum_profiles:minimumProfiles,
    status:accepted.length===0?'empty':accepted.length<minimumProfiles?'collecting':'available',
    metrics:null
  };
  if(basic.status==='collecting')return basic;
  const total=Object.fromEntries(COUNT_FIELDS.map(k=>[k,0]));
  let active=0,repeat=0,activePassports=0,discoveryProfiles=0,partialDiscovery=0;
  const discovery={models:0,agents:0,mcp_servers:0,applications_and_processes:0};
  const coverage={models:0,agents:0,mcp_servers:0,applications_and_processes:0};
  for(const payload of accepted){
    for(const w of payload.weeks){
      if(w.start<day(first) || w.start>current)continue;
      for(const key of COUNT_FIELDS)total[key]+=w[key];
      if(w.start===current){
        active+=Number(w.active_days>0);repeat+=Number(w.active_days>=2);
        activePassports+=w.active_passports;
      }
    }
    const d=payload.latest_discovery;
    if(d && date(d.observed_on)>=shift(today,-6)){
      discoveryProfiles++;partialDiscovery+=Number(d.partial);
      for(const key of Object.keys(discovery))if(d[key]!==null){discovery[key]+=d[key];coverage[key]++;}
    }
  }
  basic.metrics={
    reporting_profiles:accepted.length,weekly_active_profiles:active,
    weekly_repeat_profiles:repeat,repeat_check_rate_basis_points:active?Math.floor(repeat*10000/active):null,
    successful_scans:total.successful_scans,scan_attempts:total.scans,
    weekly_active_passports:activePassports,receipts:total.receipts,
    meaningful_changes:total.meaningful_changes,during_changes:total.during_changes,between_changes:total.between_changes,
    reconstructable_changes:total.reconstructable_changes,
    reconstructable_change_rate_basis_points:total.meaningful_changes && !total.incomplete_history_receipts?Math.floor(total.reconstructable_changes*10000/total.meaningful_changes):null,
    partial_receipts:total.partial_receipts,incomplete_history_receipts:total.incomplete_history_receipts,
    passport_versions_created:total.passport_versions_created,
    latest_discovery:Object.fromEntries(Object.entries(discovery).map(([k,v])=>[k,coverage[k]?v:null])),
    discovery_profile_coverage:coverage,discovery_profiles:discoveryProfiles,partial_discovery_profiles:partialDiscovery,
    total_installs:null
  };
  return basic;
}

export function createHandler({pool,secret,enabled=false,environment='validation',protocol='manual',
  clock=()=>new Date(),minimumProfiles=5,maxProfiles=10000,perAddressPerHour=120,globalPerHour=5000,
  tlsTerminated=false,allowLocalHttp=false,remoteAddress=req=>req.socket.remoteAddress}={}) {
  if(!['manual','usage'].includes(protocol) || !pool || !Buffer.isBuffer(secret) || secret.length!==32 || !['validation','production'].includes(environment)
    || [enabled,tlsTerminated,allowLocalHttp].some(v=>typeof v!=='boolean')
    || !Number.isInteger(minimumProfiles) || minimumProfiles<5 || minimumProfiles>maxProfiles
    || !Number.isInteger(maxProfiles) || maxProfiles<5 || maxProfiles>10000
    || !Number.isInteger(perAddressPerHour) || perAddressPerHour<1 || perAddressPerHour>1000000
    || !Number.isInteger(globalPerHour) || globalPerHour<1 || globalPerHour>1000000) throw new Error('invalid_collector_configuration');
  const usage=protocol==='usage', table=usage?'radar_metrics.installations':'radar_metrics.surfaces';
  const endpoint=BASE+(usage?'/usage':'/metrics');
  const route=usage?new RegExp(SURFACE.source.replace('surfaces','installations')):SURFACE;
  const decode=usage?parseUsage:parse, summarize=usage?aggregateUsage:aggregate;
  const sql=q=>q.replaceAll('radar_metrics.surfaces',table);
  const h=(domain,value)=>createHmac('sha256',secret).update((usage?'usage-v2:':'')+domain+'\n'+value).digest('hex');
  const authorize=(row,credential)=>{if(!same(row.credential_hash,h('credential',credential)))reject(401,'unauthorized');};
  async function rate(address,now) {
    // Shared PostgreSQL counters, keyed by HMAC; raw IPs are never stored.
    // Do not trust forwarded headers here. Inject a configured trusted-proxy
    // resolver in an existing Express deployment if its topology requires one.
    const hour=new Date(now);hour.setUTCMinutes(0,0,0);
    return transaction(pool,async db=>{
      await db.query("DELETE FROM radar_metrics.rate_limits WHERE hour < $1", [shift(now,-1/12)]);
      for(const [key,limit] of [[h('rate','global'),globalPerHour],[h('rate',address||'unknown'),perAddressPerHour]]){
        const r=await db.query("INSERT INTO radar_metrics.rate_limits VALUES ($1,$2,1) ON CONFLICT(key_hash,hour) DO UPDATE SET hits=radar_metrics.rate_limits.hits+1 RETURNING hits",[key,hour]);
        if(r.rows[0].hits>limit)return false;
      }
      return true;
    });
  }
  async function surfaceSlot(db,key,credential,now) {
    await db.query("SELECT pg_advisory_xact_lock(hashtextextended($1, 11011))",[key]);
    let row=(await db.query(sql("SELECT * FROM radar_metrics.surfaces WHERE surface_hash=$1 FOR UPDATE"),[key])).rows[0];
    if(row){authorize(row,credential);return row;}
    await db.query('SELECT pg_advisory_xact_lock(110110011)');
    const count=Number((await db.query(sql('SELECT COUNT(*) AS count FROM radar_metrics.surfaces'))).rows[0].count);
    if(count>=maxProfiles)reject(503,'capacity_limit');
    await db.query(sql("INSERT INTO radar_metrics.surfaces VALUES($1,$2,0,NULL,NULL,$3,false)"),[key,h('credential',credential),now]);
    row={sequence:0,withdrawn:false,payload_digest:null};
    return row;
  }
  return async function handler(req,res,next){
    const url=req.originalUrl||req.url;
    if(url!==endpoint && !route.test(url)){
      if(typeof next==='function')return next();
      return response(res,404,{error:'not_found'});
    }
    try{
      if(!enabled)reject(503,'reporting_not_enabled');
      if(req.method==='GET' && url===endpoint){
        const now=clock();
        if(!await rate(remoteAddress(req),now))reject(429,'rate_limited');
        const rows=await transaction(pool,async db=>{
          // Expire bodies physically, while retaining minimal authentication and
          // sequence metadata so replays cannot become new contributions.
          await db.query(sql("UPDATE radar_metrics.surfaces SET payload=NULL,payload_digest=NULL WHERE payload IS NOT NULL AND updated_at < $1"),[shift(now,usage?-35:-31)]);
          return (await db.query(sql("SELECT payload FROM radar_metrics.surfaces WHERE NOT withdrawn AND payload IS NOT NULL AND updated_at >= $1 AND (payload->>'generated_on') >= $2 ORDER BY surface_hash LIMIT $3"),[shift(now,usage?-29:-7),day(shift(date(day(now)),usage?-28:-7)),maxProfiles+1])).rows;
        });
        if(rows.length>maxProfiles)reject(503,'capacity_limit');
        return response(res,200,summarize(rows,now,{environment,minimumProfiles}));
      }
      const match=route.exec(url);
      if(!match || !['PUT','DELETE'].includes(req.method))reject(405,'method_not_allowed');
      if(!req.socket.encrypted && !tlsTerminated && !(environment==='validation' && allowLocalHttp && loopback(req.socket.remoteAddress)))reject(426,'https_required');
      if(req.headers.origin || req.headers['content-encoding'] || req.headers['transfer-encoding'])reject(400,'unsupported_request');
      const authorization=TOKEN.exec(req.headers.authorization||'');
      if(!authorization)reject(401,'unauthorized');
      if(req.headers['content-type']!=='application/json')reject(415,'application_json_required');
      const length=req.headers['content-length']??(req.method==='DELETE'?'0':'');
      if(!/^[0-9]{1,5}$/.test(length) || Number(length)>MAX_WIRE)reject(413,'payload_limit');
      if(req.body!==undefined)reject(500,'mount_before_body_parser');
      const now=clock();
      if(!await rate(remoteAddress(req),now))reject(429,'rate_limited');
      const raw=await read(req);
      if(raw.length!==Number(length))reject(400,'content_length_mismatch');
      const key=h('surface',match[1]),credential=authorization[1];
      if(req.method==='DELETE'){
        if(raw.length)reject(400,'withdrawal_body_must_be_empty');
        await transaction(pool,async db=>{
          await surfaceSlot(db,key,credential,now);
          await db.query(sql("UPDATE radar_metrics.surfaces SET payload=NULL,payload_digest=NULL,withdrawn=true WHERE surface_hash=$1"),[key]);
        });
        return response(res,204);
      }
      let payload;
      try{payload=decode(raw,now);if(usage && payload.audience!==(environment==='production'?'community':'validation'))throw new Error('wrong_audience');}catch{reject(400,'invalid_aggregate');}
      const payloadDigest=createHash('sha256').update(raw).digest('hex');
      const outcome=await transaction(pool,async db=>{
        const row=await surfaceSlot(db,key,credential,now);
        if(row.withdrawn)reject(410,'surface_withdrawn');
        const sequence=Number(row.sequence);
        if(payload.sequence===sequence && payloadDigest===row.payload_digest)return 'unchanged';
        if(payload.sequence<=sequence)reject(409,'sequence_conflict');
        await db.query(sql("UPDATE radar_metrics.surfaces SET payload=$2::jsonb,payload_digest=$3,sequence=$4,updated_at=$5 WHERE surface_hash=$1"),[key,canonical(payload),payloadDigest,payload.sequence,now]);
        return 'stored';
      });
      return response(res,200,{schema_version:usage?'2.0':'1.0',status:outcome,accepted_sequence:payload.sequence,payload_sha256:payloadDigest});
    }catch(error){
      // Never log request data, URLs, credentials, SQL values, IPs or error text.
      res.setHeader('Connection','close');
      return response(res,error instanceof Failure?error.status:503,{error:error instanceof Failure?error.code:'collector_unavailable'});
    }
  };
}
