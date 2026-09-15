/** Scheduled externally once daily, even with no public requests. */
export async function cleanup(pool,now=new Date()){
  const db=await pool.connect();
  try{
    await db.query('BEGIN');
    await db.query("SET LOCAL statement_timeout='5s'");
    await db.query("SET LOCAL lock_timeout='2s'");
    await db.query('UPDATE radar_metrics.installations SET payload=NULL,payload_digest=NULL WHERE payload IS NOT NULL AND updated_at < $1',[new Date(now.getTime()-35*86400000)]);
    await db.query('UPDATE radar_metrics.surfaces SET payload=NULL,payload_digest=NULL WHERE payload IS NOT NULL AND updated_at < $1',[new Date(now.getTime()-31*86400000)]);
    await db.query('DELETE FROM radar_metrics.rate_limits WHERE hour < $1',[new Date(now.getTime()-2*3600000)]);
    await db.query('COMMIT');
  }catch(e){await db.query('ROLLBACK').catch(()=>{});throw e;}
  finally{db.release();}
}
export async function health(pool){
  try{
    const r=await pool.query("SELECT to_regclass('radar_metrics.installations') IS NOT NULL AND to_regclass('radar_metrics.rate_limits') IS NOT NULL AS ready");
    return r.rows[0].ready===true;
  }catch{return false;}
}
