const {spawn,spawnSync}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');const http=require('node:http');const {randomUUID}=require('node:crypto');
const root=path.resolve(__dirname,'..');const web=path.join(root,'apps/web');
const venvPython=path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const python=fs.existsSync(venvPython)?venvPython:'python';
const env={...process.env,FACTORY_NEXT_DIST_DIR:`.next-e2e-${randomUUID()}`,PYTHONPATH:path.join(root,'services/api'),FACTORY_DISABLE_WORKER:'1',API_PORT:'8001',WEB_PORT:'3001',NEXT_PUBLIC_API_URL:'http://127.0.0.1:8001',NEXT_TELEMETRY_DISABLED:'1',DATABASE_URL:'sqlite:///'+path.join(root,`data/e2e-${randomUUID()}.db`),STORAGE_ROOT:path.join(root,'data/e2e'),OUTPUT_DIR:path.join(root,'output/e2e'),ASSETS_DIR:path.join(root,'data/e2e-assets')};
const owned=[];let errors='';
function start(bin,args){const p=spawn(bin,args,{cwd:web,env,windowsHide:true,stdio:['ignore','ignore','pipe'],detached:process.platform!=='win32'});p.stderr.on('data',b=>errors=(errors+b.toString()).slice(-8000));owned.push(p);return p;}
async function reachable(url){return new Promise(resolve=>{const req=http.get(url,r=>{r.resume();resolve(r.statusCode===200);});req.on('error',()=>resolve(false));req.setTimeout(1000,()=>{req.destroy();resolve(false);});});}
async function waitFor(url,p){const deadline=Date.now()+180000;while(Date.now()<deadline){if(p.exitCode!==null)throw new Error('Test server exited. '+errors);if(await reachable(url))return;await new Promise(r=>setTimeout(r,500));}throw new Error('Test server timeout. '+errors);}
function cleanup(){for(const p of owned.reverse()){if(p.exitCode!==null)continue;try{if(process.platform==='win32')spawnSync('taskkill.exe',['/PID',String(p.pid),'/T','/F'],{stdio:'ignore',windowsHide:true,timeout:10000});else process.kill(-p.pid,'SIGTERM');}catch{}try{p.kill();}catch{}}}
process.on('SIGINT',()=>{cleanup();process.exit(130);});process.on('SIGTERM',()=>{cleanup();process.exit(143);});
(async()=>{let result=1;try{if(await reachable('http://127.0.0.1:8001/health')||await reachable('http://127.0.0.1:3001'))throw new Error('Test ports 8001/3001 are already in use; existing servers will not be reused or terminated.');
const api=start(python,['-m','uvicorn','factory.main:app','--host','127.0.0.1','--port','8001','--no-access-log']);await waitFor('http://127.0.0.1:8001/health',api);
const ui=start(process.execPath,[path.join(web,'node_modules/next/dist/bin/next'),'dev','--hostname','127.0.0.1','--port','3001']);await waitFor('http://127.0.0.1:3001',ui);
const tests=spawn(process.execPath,[path.join(web,'node_modules/@playwright/test/cli.js'),'test'],{cwd:web,env,stdio:'inherit',windowsHide:true});owned.push(tests);result=await new Promise(resolve=>tests.on('exit',code=>resolve(code??1)));
}catch(e){console.error(e.message);}finally{cleanup();}process.exit(result);})();
