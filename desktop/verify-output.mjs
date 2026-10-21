// Reopen previously generated native Maximum outputs in the current build; no repeated inference.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const previous=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_inference.json')));
assert.equal(previous.status,'PASS_REAL_NATIVE_GPU_PIPELINE');
const run=previous.run;const errors=[];const checks=[];const shutdownNetworkEvents=[];let shuttingDown=false;
const child=spawn(path.join(root,'dist/windows/latest/Asset Forge Studio.exe'),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:path.join(run,'config'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port=19388'},stdio:'ignore',windowsHide:false});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page,runtime;
async function api(route,body){const r=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});assert(r.ok,`API ${route}: ${r.status}`);return r.json();}
const result={status:'RUNNING',run,checks,errors,shutdownNetworkEvents,scope:'Real native output reopening, texture loading, export, configuration revision; no artistic approval',meshy_parity:'NOT_TESTED'};
try{
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:19388');break;}catch{await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.on('console',m=>{if(m.type()==='error'){if(shuttingDown&&m.text().includes('ERR_CONNECTION_REFUSED')){shutdownNetworkEvents.push('Expected polling request failed after managed backend shutdown');return;}errors.push(m.text().replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]'));}});page.on('pageerror',e=>errors.push(e.message));
 await page.locator('.studio-sidebar').waitFor({timeout:180000});runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const snapshot=await api('/api/studio?project_id=runavelle');
 for(const name of ['Archer Tower Maximum Single QA','Archer Tower Maximum Batch QA']){
  const asset=snapshot.assets.find(a=>a.name===name);assert(asset&&asset.versions.length>=2);
  await page.evaluate(id=>{location.hash=`create/${id}`;},asset.id);await page.reload();
  await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0&&Number(document.querySelector('.viewer')?.dataset.textures)>0,null,{timeout:120000});
  await page.screenshot({path:path.join(run,name.includes('Single')?'native-single-textured.png':'native-batch-textured.png'),fullPage:true});
  const model=asset.versions.at(-1);const exported=await api(`/api/assets/${asset.id}/export`,{artifact_id:model.id,preset:'Master',format:'glb',request_id:crypto.randomUUID()});assert(exported.files.some(f=>f.kind==='project_bundle'));const master=exported.files.find(f=>f.name==='Master.glb');assert(master);
  const bytes=await fetch(runtime.api_base+master.url,{headers:{'X-AFS-Token':runtime.api_token}}).then(r=>r.arrayBuffer());assert(bytes.byteLength>1000000);
  checks.push({name:'actual_textured_model_and_export',asset_id:asset.id,version:model.id,texture_count:await page.locator('.viewer').getAttribute('data-textures'),glb_bytes:bytes.byteLength,passed:true});
 }
 const batches=await api('/api/batches?project_id=runavelle');const batch=batches.find(b=>b.name==='Desktop Maximum parity QA');assert(batch);
 const original=batch.items[0];const revision=await api(`/api/batches/${batch.id}/items/${original.asset_id}`,{prompt:original.prompt+' Review revision; do not regenerate automatically.'});
 const changed=revision.items[0];assert.equal(changed.attempt,original.attempt+1);assert.equal(changed.started,false);assert.deepEqual(changed.versions.map(v=>v.id),original.versions.map(v=>v.id));
 assert((await api('/api/jobs')).every(j=>j.status==='REVIEW_REQUIRED'));
 checks.push({name:'completed_batch_configuration_revision_preserves_real_outputs_and_requires_run',passed:true,attempt:changed.attempt});
 assert.equal(errors.length,0,errors.join('\n'));
 shuttingDown=true;await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<180&&child.exitCode===null;n++)await sleep(500);assert.notEqual(child.exitCode,null);result.status='PASS_REAL_TEXTURED_NATIVE_OUTPUT';
}catch(e){result.status='FAILED';result.failure=String(e).replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]');process.exitCode=1;}
finally{if(browser)await browser.close().catch(()=>{});fs.writeFileSync(path.join(run,'output-report.json'),JSON.stringify(result,null,2));fs.writeFileSync(path.join(root,'docs/evidence/desktop_output.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));}
