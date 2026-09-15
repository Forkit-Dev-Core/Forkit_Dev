/** Task-owned real HTTP/PostgreSQL validation and optional local browser preview. */
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {Pool} from 'pg';
import {createHandler} from '../collector.mjs';

const root=fileURLToPath(new URL('../../../../',import.meta.url));
const python=process.env.RADAR_TEST_PYTHON||path.join(root,'.radar-venv/bin/python');
if(!process.env.RADAR_TEST_DATABASE_URL)throw new Error('Select a disposable RADAR_TEST_DATABASE_URL');
const output=path.resolve(process.env.RADAR_TEST_OUTPUT||path.join(root,'output/radar-prompt11/http-workflow'));
await fs.mkdir(output,{recursive:true});
const pool=new Pool({connectionString:process.env.RADAR_TEST_DATABASE_URL,max:8,connectionTimeoutMillis:5000});
const database=(await pool.query('SELECT current_database() AS name')).rows[0].name;
if(!/^forkit_p11_/.test(database))throw new Error('Only a disposable forkit_p11_* database may be used');
await pool.query(await fs.readFile(new URL('../schema.sql',import.meta.url),'utf8'));
await pool.query('TRUNCATE radar_metrics.surfaces,radar_metrics.rate_limits');
const handler=createHandler({pool,secret:randomBytes(32),enabled:true,allowLocalHttp:true,perAddressPerHour:600});
const site=path.join(root,'packages/radar/site');
const files=new Map([['/','index.html'],['/index.html','index.html'],['/styles.css','styles.css'],['/page.js','page.js'],['/metrics.js','metrics.js'],['/example-card.html','example-card.html']]);
const server=http.createServer({maxHeaderSize:8192},async(req,res)=>{
  const name=files.get(req.url);
  if(name&&req.method==='GET'){
    res.setHeader('Content-Type',name.endsWith('.css')?'text/css':name.endsWith('.js')?'text/javascript':'text/html');
    res.setHeader('Cache-Control','no-store');
    res.end(await fs.readFile(path.join(site,name)));
  }else await handler(req,res);
});
server.requestTimeout=10000;server.headersTimeout=10000;
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
try{
  const code=await new Promise((resolve,reject)=>{
    const child=spawn(python,[path.join(root,'scripts/check_radar_reporting_http.py'),'--endpoint',origin+'/api/v1/radar','--output',output],{stdio:['ignore','inherit','inherit'],env:{...process.env,PYTHONPATH:''}});
    child.once('error',reject);child.once('exit',resolve);
  });
  if(code!==0)throw new Error('Installed client HTTP workflow failed');
  await fs.writeFile(path.join(output,'service.json'),JSON.stringify({origin,environment:'validation',node:process.version,postgres:(await pool.query('SELECT version() AS version')).rows[0].version,scope:'Task-owned local fixture database and loopback server; not deployed'},null,2));
  console.log('Local validation preview: '+origin+'/#activity');
  if(process.argv.includes('--keep-open')){
    await new Promise(resolve=>{process.once('SIGTERM',resolve);process.once('SIGINT',resolve);});
  }
}finally{
  await new Promise(resolve=>server.close(resolve));await pool.end();
}

