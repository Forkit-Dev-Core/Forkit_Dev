// Fixed ASCII contract: canonical JSON is equivalent to JCS for these fields.
export const MAX_WIRE = 32768;
export const COUNT_FIELDS = ['active_days','scans','successful_scans','receipts','meaningful_changes','during_changes','between_changes','reconstructable_changes','incomplete_history_receipts','partial_receipts','active_passports','passport_versions_created'];
export function keys(value, expected) {
  return value !== null && !Array.isArray(value) && typeof value === 'object'
    && Object.keys(value).sort().join('\0') === [...expected].sort().join('\0');
}
export function integer(value, max=100000000) {
  return Number.isSafeInteger(value) && value >= 0 && value <= max;
}
export function date(value) {
  if(typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) throw new Error('invalid_date');
  const d = new Date(value+'T00:00:00Z');
  if(!Number.isFinite(d.getTime()) || d.toISOString().slice(0,10)!==value) throw new Error('invalid_date');
  return d;
}
export const day = d => d.toISOString().slice(0,10);
export const shift = (d,n) => new Date(d.getTime()+n*86400000);
export const monday = d => shift(d,-((d.getUTCDay()+6)%7));
export function canonical(v) {
  if(Array.isArray(v)) return '['+v.map(canonical).join(',')+']';
  if(v!==null && typeof v==='object') return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
export function validate(value, now) {
  if(!keys(value,['schema_version','kind','policy','sequence','generated_on','weeks','latest_discovery'])
    || value.schema_version!=='1.0' || value.kind!=='forkit_usage_contribution' || value.policy!=='session-metrics-v1'
    || !integer(value.sequence,1000000000) || value.sequence<1 || !Array.isArray(value.weeks) || value.weeks.length!==4) throw new Error('invalid_contribution');
  const generated=date(value.generated_on), today=date(day(now)), first=shift(monday(generated),-21);
  if(generated>today || generated<shift(today,-7)) throw new Error('stale_or_future_contribution');
  value.weeks.forEach((w,i)=>{
    if(!keys(w,['start',...COUNT_FIELDS]) || COUNT_FIELDS.some(k=>!integer(w[k]))
      || w.start!==day(shift(first,i*7)) || w.active_days>7
      || (i===3 && w.active_days>((generated.getUTCDay()+6)%7)+1)
      || w.successful_scans>w.scans || w.active_days>w.scans+w.receipts
      || w.meaningful_changes!==w.during_changes+w.between_changes || w.reconstructable_changes>w.during_changes
      || w.incomplete_history_receipts>w.receipts || w.partial_receipts>w.receipts
      || w.active_passports>w.receipts*2 || (!w.receipts && w.meaningful_changes)) throw new Error('invalid_week');
  });
  const d=value.latest_discovery;
  if(d!==null){
    if(!keys(d,['observed_on','models','agents','mcp_servers','applications_and_processes','partial'])
      || ['models','agents','mcp_servers','applications_and_processes'].some(k=>d[k]!==null&&!integer(d[k]))
      || typeof d.partial!=='boolean' || date(d.observed_on)<first || date(d.observed_on)>generated) throw new Error('invalid_discovery');
  }
  return value;
}
export function parse(raw,now) {
  if(!Buffer.isBuffer(raw) || raw.length>MAX_WIRE) throw new Error('invalid_size');
  const value=validate(JSON.parse(raw.toString('utf8')),now);
  // Reject duplicate keys, extra whitespace, alternate numeric spellings, BOM,
  // malformed UTF-8 and unknown values rather than accepting a changed preview.
  if(!Buffer.from(canonical(value),'utf8').equals(raw)) throw new Error('canonical_json_required');
  return value;
}
