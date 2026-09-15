/** Operator/development runner; no deployment or migration happens implicitly. */
import http from 'node:http';
import fs from 'node:fs/promises';
import {Pool} from 'pg';
import {createHandler} from './collector.mjs';
import {cleanup,health} from './maintenance.mjs';

if(!process.env.RADAR_METRICS_DATABASE_URL || !/^[a-f0-9]{64}$/.test(process.env.RADAR_METRICS_SECRET||'')) {
  throw new Error('Provide the selected collector database URL and a private 32-byte hex secret.');
}
const pool=new Pool({connectionString:process.env.RADAR_METRICS_DATABASE_URL,max:8,connectionTimeoutMillis:5000});
if(process.argv.includes('--migrate')){
  await pool.query(await fs.readFile(new URL('./schema.sql',import.meta.url),'utf8'));
  await pool.query(await fs.readFile(new URL('./usage-schema.sql',import.meta.url),'utf8'));
  await pool.end();
}else if(process.argv.includes('--cleanup')){
  await cleanup(pool);
  await pool.end();
}else{
  const options={pool,secret:Buffer.from(process.env.RADAR_METRICS_SECRET,'hex'),
    environment:process.env.RADAR_METRICS_ENVIRONMENT==='production'?'production':'validation',
    tlsTerminated:process.env.RADAR_METRICS_TLS_TERMINATED==='1',
    allowLocalHttp:process.env.RADAR_METRICS_ALLOW_LOCAL_HTTP==='1'};
  const manual=createHandler({...options,enabled:process.env.RADAR_METRICS_ENABLED==='1'});
  const usage=createHandler({...options,protocol:'usage',enabled:process.env.RADAR_USAGE_ENABLED==='1'});
  const server=http.createServer({maxHeaderSize:8192},async(req,res)=>{
    if(req.url==='/health'&&req.method==='GET'){
      res.statusCode=await health(pool)?200:503;res.setHeader('Cache-Control','no-store');
      res.end(res.statusCode===200?'ready':'unavailable');return;
    }
    return usage(req,res,()=>manual(req,res));
  });
  server.requestTimeout=10000;server.headersTimeout=10000;server.keepAliveTimeout=1000;
  const port=Number(process.env.RADAR_METRICS_PORT||8766);
  if(!Number.isInteger(port)||port<1||port>65535)throw new Error('Invalid local collector port');
  server.listen(port,'127.0.0.1',()=>console.log('Local aggregate collector listening on 127.0.0.1:'+port));
  const stop=()=>server.close(()=>pool.end().finally(()=>process.exit(0)));
  process.once('SIGTERM',stop);process.once('SIGINT',stop);
}
