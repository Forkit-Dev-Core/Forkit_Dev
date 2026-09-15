/* Only public aggregates from an explicit same-origin endpoint. No visitor telemetry. */
'use strict';
const activity=document.getElementById('activity');
const grid=document.getElementById('metrics-grid');
const message=document.getElementById('metrics-state');
const windowLabel=document.getElementById('metrics-window');
const notes=document.getElementById('metrics-notes');
const refresh=document.getElementById('refresh-metrics');
const count=n=>Number.isSafeInteger(n)&&n>=0&&n<=Number.MAX_SAFE_INTEGER;
const fields=['reporting_profiles','weekly_active_profiles','weekly_repeat_profiles','repeat_check_rate_basis_points','successful_scans','scan_attempts','weekly_active_passports','receipts','meaningful_changes','during_changes','between_changes','reconstructable_changes','reconstructable_change_rate_basis_points','partial_receipts','incomplete_history_receipts','passport_versions_created','latest_discovery','discovery_profile_coverage','discovery_profiles','partial_discovery_profiles','total_installs'];
function exact(v,keys){return v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');}
function day(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const date=new Date(value+'T00:00:00.000Z');
  return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value?date:null;
}
function valid(v){
  if(!exact(v,['schema_version','kind','policy','environment','generated_at','window_start','window_end','week_start','minimum_profiles','status','metrics'])
    ||v.schema_version!=='1.0'||v.kind!=='forkit_public_metrics'||v.policy!=='session-metrics-v1'
    ||!['production','validation'].includes(v.environment)||!['empty','collecting','available'].includes(v.status)
    ||!count(v.minimum_profiles)||v.minimum_profiles<5
    ||!['window_start','window_end','week_start'].every(k=>day(v[k]))
    ||typeof v.generated_at!=='string'||!Number.isFinite(Date.parse(v.generated_at)))return false;
  const generated=new Date(v.generated_at),week=day(v.week_start),end=day(v.window_end);
  if(week.getUTCDay()!==1||end.toISOString().slice(0,10)!==generated.toISOString().slice(0,10)
    ||end-week<0||end-week>=7*86400000||week-day(v.window_start)!==21*86400000)return false;
  if(v.status==='collecting')return v.metrics===null;
  const m=v.metrics;
  if(!exact(m,fields)||m.total_installs!==null
    ||!exact(m.latest_discovery,['models','agents','mcp_servers','applications_and_processes'])
    ||!exact(m.discovery_profile_coverage,['models','agents','mcp_servers','applications_and_processes'])
    ||Object.values(m.latest_discovery).some(n=>n!==null&&!count(n))
    ||Object.values(m.discovery_profile_coverage).some(n=>!count(n)||n>m.discovery_profiles)
    ||Object.keys(m.latest_discovery).some(k=>(m.latest_discovery[k]===null)!==(m.discovery_profile_coverage[k]===0)))return false;
  const rates=['repeat_check_rate_basis_points','reconstructable_change_rate_basis_points'];
  if(fields.filter(k=>!['latest_discovery','discovery_profile_coverage','total_installs',...rates].includes(k)).some(k=>!count(m[k]))
    ||rates.some(k=>m[k]!==null&&(!count(m[k])||m[k]>10000))
    ||m.successful_scans>m.scan_attempts||m.weekly_repeat_profiles>m.weekly_active_profiles
    ||m.weekly_active_profiles>m.reporting_profiles||m.reconstructable_changes>m.during_changes
    ||m.meaningful_changes!==m.during_changes+m.between_changes
    ||m.partial_receipts>m.receipts||m.incomplete_history_receipts>m.receipts
    ||m.partial_discovery_profiles>m.discovery_profiles||m.discovery_profiles>m.reporting_profiles)return false;
  if(v.status==='empty'&&m.reporting_profiles!==0||v.status==='available'&&m.reporting_profiles<v.minimum_profiles)return false;
  if(v.status==='empty'&&fields.filter(k=>typeof m[k]==='number').some(k=>m[k]!==0))return false;
  const repeat=m.weekly_active_profiles?Math.floor(m.weekly_repeat_profiles*10000/m.weekly_active_profiles):null;
  const reconstruct=m.meaningful_changes&&!m.incomplete_history_receipts?Math.floor(m.reconstructable_changes*10000/m.meaningful_changes):null;
  return m.repeat_check_rate_basis_points===repeat&&m.reconstructable_change_rate_basis_points===reconstruct;
}
function tile(label,value,detail){
  const card=document.createElement('div');card.className='metric-card';
  const name=document.createElement('h3');name.textContent=label;
  const number=document.createElement('strong');number.textContent=value;
  const explanation=document.createElement('p');explanation.textContent=detail;
  card.append(name,number,explanation);grid.append(card);
}
const number=n=>n===null?'—':new Intl.NumberFormat().format(n);
const percentage=n=>n===null?'—':(n/100).toFixed(1)+'%';
async function loadMetrics(){
  refresh.disabled=true;grid.replaceChildren();windowLabel.textContent='';
  message.textContent='Checking for a current aggregate report…';
  notes.textContent='Private installs and offline activity cannot be counted by the website.';
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
  try{
    if(!['http:','https:'].includes(location.protocol))throw new Error('unavailable');
    const url=new URL(activity.dataset.metricsEndpoint,location.href);
    if(url.origin!==location.origin||url.search||url.hash||url.pathname!=='/api/v1/radar/metrics')throw new Error('invalid_endpoint');
    const response=await fetch(url,{signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer',headers:{Accept:'application/json'}});
    if(!response.ok)throw new Error('unavailable');
    const reader=response.body.getReader(),chunks=[];let size=0;
    while(true){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>16384){await reader.cancel();throw new Error('oversized');}chunks.push(part.value);}
    const raw=new Uint8Array(size);let cursor=0;for(const chunk of chunks){raw.set(chunk,cursor);cursor+=chunk.length;}
    const v=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
    if(!valid(v))throw new Error('invalid');
    const age=Date.now()-Date.parse(v.generated_at);
    if(age>15*60000||age< -120000){message.textContent='The aggregate report is stale. Current activity numbers are unavailable.';return;}
    const label=v.environment==='validation'?'LOCAL VALIDATION DATA · ':'';
    if(v.status==='collecting'){message.textContent=label+'Waiting for at least '+v.minimum_profiles+' current reporting profiles. Individual counts are not shown.';return;}
    message.textContent=label+(v.status==='empty'?'The connected collector has no current contributions.':'Current self-reported community activity.');
    windowLabel.textContent='UTC window: '+v.window_start+' through '+v.window_end+' · This week starts '+v.week_start+' · Updated '+new Date(v.generated_at).toLocaleString();
    const m=v.metrics;
    tile('Reporting profiles',number(m.reporting_profiles),'Current opt-in profiles · total installs are unknown');
    tile('Successful scans',number(m.successful_scans),number(m.scan_attempts)+' recorded attempts in this window');
    tile('Weekly Active Passports',number(m.weekly_active_passports),'Distinct within each profile · references can overlap across profiles');
    tile('Repeat-check rate',percentage(m.repeat_check_rate_basis_points),number(m.weekly_repeat_profiles)+' of '+number(m.weekly_active_profiles)+' active profiles returned on another UTC day');
    tile('Session Receipts',number(m.receipts),'Recorded receipts in this four-week window');
    tile('Meaningful changes',number(m.meaningful_changes),number(m.during_changes)+' during sessions · '+number(m.between_changes)+' between captures');
    tile('Passport versions created',number(m.passport_versions_created),'Distinct Core IDs created through Radar while reporting was enabled');
    tile('Reconstructable changes',percentage(m.reconstructable_change_rate_basis_points),number(m.reconstructable_changes)+' of '+number(m.meaningful_changes)+' recorded events have a local trace');
    tile('Model observations',number(m.latest_discovery.models),'Comparable model observations from '+number(m.discovery_profile_coverage.models)+' profiles in the last seven UTC dates');
    tile('Agent observations',number(m.latest_discovery.agents),'Comparable agent observations from '+number(m.discovery_profile_coverage.agents)+' profiles · runtime use unverified');
    notes.textContent=number(m.partial_receipts)+' receipts have partial coverage; '+number(m.incomplete_history_receipts)+' lack complete count evidence. '+number(m.partial_discovery_profiles)+' latest scans are partial. Counts are self-reported and can include repeated systems across profiles. '+(v.environment==='validation'?'These are validation fixtures, not user traction.':'No count establishes unique people, authenticated AI execution or universal system visibility.');
  }catch{
    grid.replaceChildren();message.textContent='Not connected to a current collector. Activity numbers are unavailable.';
  }finally{clearTimeout(timeout);refresh.disabled=false;}
}
refresh.addEventListener('click',loadMetrics);
loadMetrics();
