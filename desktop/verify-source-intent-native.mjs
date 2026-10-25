// Real CPU Qwen interpretation in the packaged queue; declared mutex fixture holds GPU admission.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {createHash} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'..'),run=path.join(root,'.local/source-intent-native',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const config=path.join(run,'config'),library=path.join(run,'Library');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,'0.9.29');
const source=path.join(root,'.local/fixtures/ArcherTowerSource.png'),hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex'),sourceHash=hash(source);
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,closing=false,api,hold,batchId;
const report={status:'RUNNING',version:build.version,run,errors:[],scope:'Real local CPU Qwen Source interpretation in the actual packaged shared queue, immutable reference/prompt, no unused new-concept call, checkpoint/restart. A declared helper owns only the existing global GPU mutex so the admitted real inference job stays queued; it consumes no GPU and fabricates no inference/model. Batch is explicitly paused before releasing mutex. Full real Archer geometry/Blender/export was separately verified in 0.9.18.'};
async function open(){
 child=spawn(path.join(build.delivery_location,build.executable),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,AFS_INTENT_ENABLED:'1',WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(60000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 api=async(route,body)=>{const r=await fetch(runtime.api_base+route,{method:body?'POST':'GET',headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.clone().text());return r.json();};return runtime;
}
async function close(){closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});browser=null;page=null;closing=false;}
try{
 hold=spawn(path.join(root,'.venv/Scripts/python.exe'),['-u','-c',"from apps.api.jobs import exclusive_worker_lock; import sys;\nwith exclusive_worker_lock():\n print('GPU_HELD',flush=True)\n sys.stdin.readline()"],{cwd:root,stdio:['pipe','pipe','pipe'],windowsHide:true});
 await new Promise((resolve,reject)=>{let out='';const timeout=setTimeout(()=>reject(Error('Declared mutex helper unavailable; no test admission')),15000);hold.stdout.on('data',data=>{out+=data;if(out.includes('GPU_HELD')){clearTimeout(timeout);resolve();}});hold.on('exit',code=>{clearTimeout(timeout);reject(Error('Mutex helper exit '+code));});});
 const runtime=await open();const project=await api('/api/projects',{name:'Source interpretation / actual local Qwen'});report.project_id=project.id;
 const prompt='Reconstruct 1 archer tower from this source image. Preserve its geometry and materials, height 10 m.';
 const asset=await api('/api/assets',{project_id:project.id,name:'Source tower / actual local analysis',prompt});report.asset_id=asset.id;
 const form=new FormData();form.append('file',new Blob([fs.readFileSync(source)]),'ArcherTowerSource.png');const response=await fetch(runtime.api_base+'/api/import/reference?project_id='+project.id+'&asset_id='+asset.id,{method:'POST',headers:{'X-AFS-Token':runtime.api_token},body:form});assert(response.ok);const reference=await response.json();assert.equal(reference.sha256,sourceHash);
 const input={asset_id:asset.id,request_id:'source-analysis-no-unused-planner-0919',quality:'Maximum',reference_id:reference.id,reference_usage:'source',seeds:[43]};
 const started=Date.now();const submission=await api('/api/automation/single',input);batchId=submission.batch_id;report.batch_id=batchId;
 let ready=false,analysis,inference;
 for(let n=0;n<1200;n++){
  const jobs=await api('/api/jobs');analysis=jobs.find(j=>j.payload.kind==='prompt_analysis');inference=jobs.find(j=>j.payload.kind==='inference');
  assert(!jobs.some(j=>['FAILED','BLOCKED','CANCELLED'].includes(j.status)),JSON.stringify(jobs));
  if(analysis?.status==='REVIEW_REQUIRED'&&inference){assert.equal(inference.status,'QUEUED');ready=true;break;}
  await sleep(500);
 }assert(ready,'Real source interpretation did not finish');report.seconds_to_geometry_admission=(Date.now()-started)/1000;
 await api('/api/batches/'+batchId+'/control',{action:'pause'});
 const folder=path.join(library,'jobs',analysis.id),file=path.join(folder,'intent.json'),intent=JSON.parse(fs.readFileSync(file,'utf8'));report.actual_interpretation=intent;
 assert.equal(intent.status,'interpreted');assert.equal(intent.execution,'local_cpu_only');assert.equal(intent.model,'qwen3-vl:4b-instruct-q4_K_M');assert(intent.model_digest);assert.equal(intent.reference_role,'source');
 assert(intent.chunks.every(c=>c.concept_planning.status==='skipped'&&c.planning_duration_ns===null&&c.generation_plan.inferred_ordinary_details.length===0));
 assert.equal(intent.generation_prompt_en,intent.chunks.map(c=>c.interpretation.translated_prompt_en).join('\n'));
 assert(!fs.readFileSync(path.join(folder,'worker.log'),'utf8').includes('image-independent concept planning'));
 assert(!fs.existsSync(path.join(library,'jobs',inference.id,'process.json')));assert.equal(inference.payload.artifact_id,reference.id);
 assert.equal(inference.payload.effective_config.quality,'Maximum');assert.equal(inference.payload.effective_config.inference_steps,32);assert.equal(inference.payload.effective_config.texture.size,4096);
 assert.equal((await api('/api/automation/single',input)).batch_id,batchId);const ids=(await api('/api/jobs')).map(j=>j.id).sort();assert.equal(ids.length,2);
 await page.evaluate(id=>{localStorage.setItem('afs.project',id);location.hash='production';},project.id);await page.reload();await page.locator('.production-queue-list').getByRole('button',{name:/Source tower \/ actual local analysis/}).click();await page.locator('.production-pipeline-link').click();
 await page.locator('.production-pipeline-history').waitFor();await page.screenshot({path:path.join(run,'actual-source-interpretation.png')});
 const intentHash=hash(file);await close();await open();
 assert.deepEqual((await api('/api/jobs')).map(j=>j.id).sort(),ids);assert.equal(hash(file),intentHash);assert.equal(hash(source),sourceHash);
 const detail=await api('/api/production/assets/'+asset.id);assert.equal(detail.asset.original_prompt,prompt);assert.equal(detail.asset.art_review_status,'not_reviewed');
 assert.equal(detail.asset.resolved_specification.prompt_interpretation.status,'interpreted');assert.equal((await api('/api/batches/'+batchId)).paused,true);
 assert(!fs.existsSync(path.join(library,'jobs',inference.id,'process.json')));assert.equal(report.errors.length,0);report.job_ids=ids;report.intent_sha256=intentHash;report.status='PASS_NATIVE_REAL_SOURCE_INTERPRETATION_NO_UNUSED_PLAN';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{if(api&&batchId)await api('/api/batches/'+batchId+'/control',{action:'pause'}).catch(()=>{});await close();if(hold){hold.stdin.end('\n');for(let n=0;n<50&&hold.exitCode===null;n++)await sleep(100);if(hold.exitCode===null)hold.kill();}fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
