// Real local GPU acceptance through the packaged desktop backend. No mocked IPC/results.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {fillAssetName} from './ui-helpers.mjs';
const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/desktop-inference',new Date().toISOString().replaceAll(/[:.]/g,'-'));
fs.mkdirSync(path.join(run,'config'),{recursive:true});
const library=path.join(run,'Library');
fs.writeFileSync(path.join(run,'config/desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const exe=path.join(root,'dist/windows/latest/Asset Forge Studio.exe');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const report={status:'RUNNING',purpose:'Actual Single Maximum versus Batch Maximum local inference, technical QA only',run,checks:[],errors:[],meshy_parity:'NOT_TESTED',production_art_approval:'NOT_GIVEN'};
let child,browser,page,runtime;
const debugPort=19387;
async function launch(){
 child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:path.join(run,'config'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${debugPort}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);break;}catch{await pause(1000);}}
 assert(browser,'Native CDP connection failed');page=browser.contexts()[0].pages()[0];
 page.on('pageerror',e=>report.errors.push(e.message.replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]')));
 await page.locator('.studio-sidebar').waitFor({timeout:180000});runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
}
async function api(route,body){const r=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});if(!r.ok)throw Error(`API ${route}: ${r.status} ${await r.text()}`);return r.json();}
async function close(){await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<180&&child.exitCode===null;n++)await pause(500);assert.notEqual(child.exitCode,null,'Native close failed');await browser.close().catch(()=>{});browser=null;}
try{
 await launch();
 await page.locator('.studio-sidebar nav a[aria-label="Create"]').click();
 
 await fillAssetName(page,'Archer Tower Maximum Single QA');
 const prompt='Archer Tower T3 Runavelle. Supplied concept reference. Single and Batch Maximum reproducibility benchmark; technical QA only.';
 await page.locator('.prompt-input').fill(prompt);
 const imported=page.waitForResponse(r=>r.url().includes('/api/import/reference')&&r.request().method()==='POST');
 await page.getByLabel('Upload concept image').setInputFiles(path.join(root,'.local/fixtures/ArcherTowerSource.png'));
 const reference=await(await imported).json();
 const submitted=page.waitForResponse(r=>r.url().endsWith('/api/studio/generate')&&r.request().method()==='POST',{timeout:180000});
 await page.getByRole('button',{name:'Generate 3D',exact:true}).click();
 const response=await submitted;assert(response.ok(),await response.text());const single=(await response.json()).jobs[0];
 assert.equal(single.payload.quality,'Maximum');assert.equal(single.payload.steps,32);
 const batch=await api('/api/batches/analyze',{project_id:'runavelle',name:'Desktop Maximum parity QA',format:'json',mode:'Maximum Quality Batch',master_prompt:JSON.stringify([{name:'Archer Tower Maximum Batch QA',prompt,preferred_engine:'trellis2_community',reference_ids:[reference.id],target_width_m:6,target_depth_m:6,target_height_m:10,confirmed:true,candidates:1}])});
 const item=batch.items[0];
 await api(`/api/assets/${item.asset_id}/concepts/${reference.id}/approve`,{reviewer:'Automated pipeline QA',notes:'Supplied reference, technical comparison only; no production quality approval.'});
 const queued=await api(`/api/batches/${batch.id}/run`,{});const batched=queued.items[0].jobs.find(j=>j.payload.kind==='inference');
 assert(batched);assert.deepEqual(single.payload.effective_config,batched.payload.effective_config);assert.equal(single.payload.effective_config_hash,batched.payload.effective_config_hash);
 report.checks.push({name:'native_single_ui_and_batch_identical_locked_configuration',passed:true,single_job:single.id,batch_job:batched.id,batch_id:batch.id,effective_config_hash:single.payload.effective_config_hash,effective_config:single.payload.effective_config});
 await page.reload();await page.locator('.studio-sidebar').waitFor();
 assert.equal((await api('/api/jobs')).filter(j=>j.payload.kind==='inference').length,2,'Refresh duplicated inference');
 const started=Date.now();let jobs;
 for(;;){jobs=await api('/api/jobs');const active=jobs.filter(j=>!['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(j.status));if(!active.length&&jobs.filter(j=>j.payload.kind==='blender').length===2)break;
  if(jobs.some(j=>['FAILED','BLOCKED','CANCELLED'].includes(j.status)))throw Error('Actual inference/postprocessing failed; inspect persisted logs');
  if(Date.now()-started>30*60*1000)throw Error('Actual inference timeout');await pause(10000);
 }
 assert(jobs.every(j=>j.status==='REVIEW_REQUIRED'));
 const model=await api('/api/studio?project_id=runavelle');
 for(const id of [single.payload.asset_id,item.asset_id])assert(model.assets.find(a=>a.id===id)?.versions.length>=2);
 const metrics=jobs.map(j=>{const folder=path.join(library,'jobs',j.id);const resources=JSON.parse(fs.readFileSync(path.join(folder,'resources.json')));const generationPath=path.join(folder,'output/generation.json');const qaPath=path.join(folder,'output/report.json');return {id:j.id,kind:j.payload.kind,status:j.status,resources:{...resources,samples:undefined},generation:fs.existsSync(generationPath)?JSON.parse(fs.readFileSync(generationPath)):undefined,qa:fs.existsSync(qaPath)?JSON.parse(fs.readFileSync(qaPath)):undefined};});
 report.jobs=metrics;
 await page.evaluate(id=>{location.hash=`create/${id}`;},single.payload.asset_id);await page.reload();await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0,null,{timeout:120000});
 await page.screenshot({path:path.join(run,'native-inference-result.png'),fullPage:true});
 report.checks.push({name:'real_gpu_and_blender_outputs_inside_native_app',passed:true});
 const oldToken=runtime.api_token;await close();await launch();assert.notEqual(runtime.api_token,oldToken);
 const reopened=await api('/api/studio?project_id=runavelle');assert(reopened.assets.find(a=>a.id===single.payload.asset_id)?.versions.length>=2);assert.equal((await api(`/api/batches/${batch.id}`)).items[0].asset_id,item.asset_id);
 await page.locator('.studio-sidebar nav a[aria-label="Library"]').click();await page.getByRole('button',{name:'Archer Tower Maximum Single QA',exact:true}).click();await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0,null,{timeout:120000});await page.screenshot({path:path.join(run,'native-inference-reopened.png'),fullPage:true});
 report.checks.push({name:'native_relaunch_preserves_actual_single_batch_models_and_jobs',passed:true});await close();assert.equal(report.errors.length,0);report.status='PASS_REAL_NATIVE_GPU_PIPELINE';
}catch(e){report.status='FAILED';report.failure=String(e).replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]');process.exitCode=1;}
finally{if(browser)await browser.close().catch(()=>{});fs.writeFileSync(path.join(run,'inference-report.json'),JSON.stringify(report,null,2));fs.writeFileSync(path.join(root,'docs/evidence/desktop_inference.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,failure:report.failure}));}
