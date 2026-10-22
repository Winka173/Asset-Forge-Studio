// Actual packaged cinematic edits, Blender renders, cache receipts and immutable versions.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import zlib from 'node:zlib';import crypto from 'node:crypto';import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'),stamp=new Date().toISOString().replaceAll(/[:.]/g,'-'),run=path.join(root,'.local/concept-layout-native',stamp),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,'')),exe=process.env.AFS_SMOKE_EXE||path.join(build.delivery_location,build.executable),server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,runtime,closing=false;
const report={status:'RUNNING',run,executable:exe,checks:[],errors:[],scope:'Actual native local Qwen interpretation, Maximum SDXL concept, inferred composition gate and bounded repair admission before 3D. GPU guard is acquired only after the real concept finishes; no simulated engine output.'};
async function api(url,body){const r=await fetch(runtime.api_base+url,{headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});assert(r.ok,`${url}: ${r.status} ${await r.clone().text()}`);return r.json();}
async function launch(){closing=false;child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{await sleep(1000);}}page=browser.contexts()[0].pages()[0];page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));}
async function close(){closing=true;await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<100&&child.exitCode===null;n++)await sleep(200);assert.notEqual(child.exitCode,null);await browser.close().catch(()=>{});browser=null;}




let hold,batchId;
async function holdGpu(){
 const code='from apps.api.jobs import exclusive_worker_lock\nimport sys,time\nfor attempt in range(1200):\n try:\n  with exclusive_worker_lock():\n   print("GPU_HELD",flush=True)\n   sys.stdin.readline()\n   break\n except OSError:time.sleep(.1)\nelse:raise RuntimeError("GPU guard timeout")';
 hold=spawn(path.join(root,'.venv/Scripts/python.exe'),['-c',code],{cwd:root,env:{...process.env,PYTHONPATH:root},windowsHide:true,stdio:['pipe','pipe','pipe']});
 await new Promise((resolve,reject)=>{let out='';hold.stdout.on('data',b=>{out+=b;if(out.includes('GPU_HELD'))resolve();});hold.on('exit',c=>reject(Error('GPU guard exited '+c)));});
}
try{
 await launch();const project=await api('/api/projects',{name:'Real concept layout guard'}),form=new FormData();form.append('file',new Blob([fs.readFileSync(path.join(root,'.local/fixtures/ArcherTowerSource.png'))],{type:'image/png'}),'ArcherTowerSource.png');
 const uploaded=await fetch(runtime.api_base+`/api/import/reference?project_id=${project.id}`,{method:'POST',headers:{'X-AFS-Token':runtime.api_token},body:form});assert(uploaded.ok);const ref=await uploaded.json();
 await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.getByRole('link',{name:'Create',exact:true}).click();await page.getByRole('button',{name:'Single asset One prompt',exact:false}).click();await page.getByRole('tab',{name:'Text + Image',exact:true}).click();
 const prompt=JSON.parse(fs.readFileSync(path.join(root,'.local/castle-reference-acceptance/report.json'),'utf8')).prompt;await page.locator('.prompt-input').fill(prompt);await page.getByLabel('Asset name',{exact:true}).fill('Castle - actual concept layout guard');await page.getByRole('combobox',{name:'Project reference',exact:true}).click();await page.getByRole('option',{name:/ArcherTowerSource/}).click();assert.equal(await page.locator('.afs-select-native[aria-label="Reference image purpose"]').inputValue(),'auto');await page.getByRole('button',{name:'Continue to generation',exact:true}).click();
 const submitted=page.waitForResponse(r=>r.url().endsWith('/api/automation/single')&&r.request().method()==='POST');await page.getByRole('button',{name:'Generate & export asset',exact:true}).click();const response=await submitted;assert(response.ok(),await response.text());const value=await response.json();batchId=value.batch_id;await page.getByRole('region',{name:'Production Workspace',exact:true}).waitFor();
 let first,layout,all;
 for(let n=0;n<900;n++){
  all=await api('/api/jobs');assert(!all.some(j=>['FAILED','BLOCKED','CANCELLED'].includes(j.status)),JSON.stringify(all));first=first?all.find(j=>j.id===first.id):all.find(j=>j.payload.kind==='concept');layout=all.find(j=>j.payload.kind==='concept_layout');
  if(!hold&&first?.status==='REVIEW_REQUIRED')await holdGpu();
  if(layout?.status==='REVIEW_REQUIRED')break;
  if(n%15===0)console.log(JSON.stringify({seconds:n,stages:all.map(j=>({kind:j.payload.kind,status:j.status}))}));
  await sleep(1000);
 }
 assert.equal(layout?.status,'REVIEW_REQUIRED');assert(hold);await api('/api/production/control',{scope:'batch',group_id:batchId,action:'pause'});
 const detail=await api('/api/production/assets/'+value.asset_id),assessment=detail.stages.find(j=>j.id===layout.id).qa;
 assert.equal(assessment.artistic_approval,false);assert.equal(detail.asset.original_prompt,prompt);const concepts=detail.artifacts.filter(a=>a.role==='concept');assert.equal(concepts.length,1);assert.equal(assessment.source_sha256,concepts[0].sha256);
 all=await api('/api/jobs');
 if(!assessment.suitable_single_asset_image){
  assert(assessment.issues.length);assert(!all.some(j=>j.payload.kind==='inference'));const repair=all.find(j=>j.payload.kind==='concept'&&j.id!==first.id);assert.equal(repair?.status,'QUEUED');assert.equal(repair.payload.effective_config.quality,'Maximum');assert.equal(repair.payload.steps,first.payload.steps);assert.equal(repair.payload.size,first.payload.size);assert.equal(repair.payload.seed,43);
 }else{assert(all.some(j=>j.payload.kind==='inference'&&j.status==='QUEUED'));}
 await page.locator('.production-pipeline-link').click();await page.locator('.production-pipeline-history').waitFor();await page.screenshot({path:path.join(run,'actual-layout-result-and-safe-next-stage.png'),fullPage:true});const before=all.map(j=>j.id).sort();await close();await launch();assert((await api('/api/batches/'+batchId)).paused);assert.deepEqual((await api('/api/jobs')).map(j=>j.id).sort(),before);assert.equal(report.errors.length,0);
 report.checks.push({name:'real_native_concept_layout_check_before_3d_and_immutable_quality_repair',passed:true,assessment,jobs:all.map(j=>({id:j.id,status:j.status,kind:j.payload.kind,quality:j.payload.quality||j.payload.effective_config?.quality,seed:j.payload.seed,steps:j.payload.steps,size:j.payload.size}))});await close();report.status='PASS_NATIVE_CONCEPT_LAYOUT_GATE';
}catch(e){report.status='FAILED';report.error=String(e);if(page)await page.screenshot({path:path.join(run,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
finally{if(browser){if(batchId)await api('/api/production/control',{scope:'batch',group_id:batchId,action:'pause'}).catch(()=>{});await close().catch(()=>{});}if(hold)hold.stdin.end('\n');fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
