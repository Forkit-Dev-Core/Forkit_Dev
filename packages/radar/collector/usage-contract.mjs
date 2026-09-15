import {MAX_WIRE,keys,integer,date,day,shift,canonical} from './contract.mjs';
export const COUNTERS=['scans','successful_scans','detection_observations','receipts','during_changes','between_changes','reconstructable_changes','partial_receipts','incomplete_history_receipts','passport_versions_created'];
export const TOOLS=['codex','claude-code','cursor','other'];
export const TOOL_FIELDS=TOOLS.map(x=>x.replace('-','_'));
export const ENGAGEMENT_COUNTERS=['viewed','history_viewed','card_exports'];
export function validateUsage(p,now,{retained=false}={}) {
  const engagement=p?.schema_version==='3.0'&&p?.policy==='usage-v3';
  const counters=engagement?[...COUNTERS,...ENGAGEMENT_COUNTERS]:COUNTERS;
  if(!keys(p,['schema_version','kind','policy','audience','sequence','generated_on','collection_complete','days','passport_windows'])
    || (!engagement&&(p.schema_version!=='2.0'||p.policy!=='usage-v2')) || p.kind!=='forkit_usage_contribution'
    || !['community','validation'].includes(p.audience) || typeof p.collection_complete!=='boolean'
    || !integer(p.sequence,1000000000) || p.sequence<1 || !Array.isArray(p.days) || p.days.length!==29
    || !Array.isArray(p.passport_windows) || p.passport_windows.length!==29)throw new Error('invalid_usage');
  const generated=date(p.generated_on),today=date(day(now));
  if(generated>today || generated<shift(today,retained?-28:-7))throw new Error('invalid_usage_date');
  p.days.forEach((r,i)=>{
    if(!keys(r,['date',...counters,'detected_tools','session_tools']) || r.date!==day(shift(generated,i-28))
      || counters.some(k=>!integer(r[k])) || !keys(r.session_tools,TOOL_FIELDS) || TOOL_FIELDS.some(k=>!integer(r.session_tools[k]))
      || (engagement&&(r.viewed>1||r.history_viewed>r.viewed))
      || !Array.isArray(r.detected_tools) || r.detected_tools.some(t=>!TOOLS.includes(t))
      || JSON.stringify([...new Set(r.detected_tools)].sort())!==JSON.stringify(r.detected_tools)
      || r.successful_scans>r.scans || r.reconstructable_changes>r.during_changes
      || r.partial_receipts>r.receipts || r.incomplete_history_receipts>r.receipts
      || (!r.receipts && r.during_changes+r.between_changes)
      || (!r.scans && (r.detection_observations || r.detected_tools.length))
      || TOOL_FIELDS.reduce((n,k)=>n+r.session_tools[k],0)!==r.receipts)throw new Error('invalid_usage_day');
    const w=p.passport_windows[i];
    if(!keys(w,['end_exclusive','distinct_passports']) || w.end_exclusive!==r.date || !integer(w.distinct_passports))throw new Error('invalid_passport_window');
    if(i>=7 && w.distinct_passports>p.days.slice(i-7,i).reduce((n,d)=>n+d.receipts*2,0))throw new Error('invalid_passport_coverage');
  });
  return p;
}
export function parseUsage(raw,now){
  if(!Buffer.isBuffer(raw)||raw.length>MAX_WIRE)throw new Error('invalid_size');
  const p=validateUsage(JSON.parse(raw.toString('utf8')),now);
  if(!Buffer.from(canonical(p)).equals(raw))throw new Error('canonical_json_required');
  return p;
}

export function aggregateUsage(rows,now,{environment='validation',minimumProfiles=5}={}){
  const end=day(now),start7=day(shift(date(end),-7)),start28=day(shift(date(end),-28));
  // Validation traffic is never promoted into production traction.
  const profiles=rows.map(r=>validateUsage(r.payload,now,{retained:true})).filter(p=>p.audience===(environment==='production'?'community':'validation'));
  const result={schema_version:'2.0',kind:'forkit_public_usage',policy:'usage-v2',environment,
    generated_at:now.toISOString(),end_exclusive:end,start_7_days:start7,start_28_days:start28,
    minimum_profiles:minimumProfiles,status:profiles.length===0?'empty':profiles.length<minimumProfiles?'collecting':'available',
    metrics:null};
  if(result.status!=='available')return result;
  const data=profiles.map(p=>({p,month:p.days.filter(d=>d.date>=start28&&d.date<end),week:p.days.filter(d=>d.date>=start7&&d.date<end)}));
  const sum=(rows,k)=>rows.reduce((n,d)=>n+d[k],0);
  const cohort=n=>n===0||n>=minimumProfiles?n:null;
  const count=(k, window='month')=>{
    const totals=data.map(d=>sum(d[window],k));
    return cohort(totals.filter(n=>n>0).length)===null?null:totals.reduce((a,b)=>a+b,0);
  };
  const active=data.filter(d=>d.week.some(r=>r.successful_scans>0||r.receipts>0));
  const repeat=active.filter(d=>d.week.filter(r=>r.successful_scans>0||r.receipts>0).length>=2);
  const complete=profiles.every(p=>p.collection_complete);
  const knownPassports=active.filter(d=>d.p.passport_windows.some(w=>w.end_exclusive===end));
  const passportTotals=knownPassports.map(d=>d.p.passport_windows.find(w=>w.end_exclusive===end).distinct_passports);
  const passportContributors=cohort(passportTotals.filter(n=>n>0).length);
  const totalChanges=data.map(d=>sum(d.month,'during_changes')+sum(d.month,'between_changes'));
  const meaningful=cohort(totalChanges.filter(n=>n>0).length)===null?null:totalChanges.reduce((a,b)=>a+b,0);
  const reconstruction=count('reconstructable_changes');
  const incomplete=data.reduce((n,d)=>n+sum(d.month,'incomplete_history_receipts'),0);
  const yesterday=day(shift(date(end),-1));
  const daily=data.filter(d=>d.p.generated_on===end);
  const dailyCount=k=>{
    const totals=daily.map(d=>d.p.days.find(r=>r.date===yesterday)?.[k]??0);
    return daily.length<minimumProfiles||cohort(totals.filter(n=>n>0).length)===null?null:totals.reduce((a,b)=>a+b,0);
  };
  const engaged=data.filter(d=>d.p.policy==='usage-v3');
  const viewers=engaged.filter(d=>d.week.some(r=>r.viewed));
  const repeatViewers=viewers.filter(d=>d.week.filter(r=>r.viewed).length>=2);
  const engagementComplete=engaged.every(d=>d.p.collection_complete);
  const cardTotals=engaged.map(d=>sum(d.week,'card_exports'));
  result.metrics={participating_profiles_28_days:profiles.length,total_installs:null,
    receipts_7_days:count('receipts', 'week'),
    daily_date:yesterday,daily_coverage_profiles:cohort(daily.length),
    receipts_yesterday:dailyCount('receipts'),during_changes_yesterday:dailyCount('during_changes'),
    engagement_policy:'usage-v3',engagement_profiles_28_days:cohort(engaged.length),
    viewing_profiles_7_days:engaged.length>=minimumProfiles?cohort(viewers.length):null,
    repeat_viewing_profiles_7_days:engaged.length>=minimumProfiles?cohort(repeatViewers.length):null,
    repeat_view_rate_basis_points:engagementComplete&&viewers.length>=minimumProfiles&&cohort(repeatViewers.length)!==null?Math.floor(repeatViewers.length*10000/viewers.length):null,
    card_exports_7_days:engaged.length>=minimumProfiles&&cohort(cardTotals.filter(n=>n>0).length)!==null?cardTotals.reduce((a,b)=>a+b,0):null,
    weekly_active_profiles:cohort(active.length),weekly_repeat_profiles:cohort(repeat.length),
    repeat_check_rate_basis_points:complete&&active.length>=minimumProfiles&&cohort(repeat.length)!==null?Math.floor(repeat.length*10000/active.length):null,
    ...Object.fromEntries(COUNTERS.map(k=>[k,count(k)])),meaningful_changes:meaningful,
    reconstructable_change_rate_basis_points:complete&&!incomplete&&meaningful&&reconstruction!==null?Math.floor(reconstruction*10000/meaningful):null,
    weekly_active_passports:complete&&active.length>=minimumProfiles&&knownPassports.length===active.length&&passportContributors!==null?
      passportTotals.reduce((a,b)=>a+b,0):null,
    passport_coverage_profiles:cohort(knownPassports.length),collection_complete:complete,
    current_snapshot_profiles:cohort(profiles.filter(p=>p.generated_on===end).length),
    detected_tool_profiles_28_days:Object.fromEntries(TOOLS.map(t=>[t,cohort(data.filter(d=>d.month.some(r=>r.detected_tools.includes(t))).length)])),
    session_tool_receipts_28_days:Object.fromEntries(TOOLS.map((t,i)=>{
      const totals=data.map(d=>d.month.reduce((n,r)=>n+r.session_tools[TOOL_FIELDS[i]],0));
      return [t,cohort(totals.filter(n=>n>0).length)===null?null:totals.reduce((a,b)=>a+b,0)];
    }))};
  return result;
}
