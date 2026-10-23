// Actual packaged SDXL + restart + two declared stale-contract negative fixtures.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';
import {spawn,execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/concept-conditioning-native',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const config=path.join(run,'config'),library=path.join(run,'Library');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,'0.9.16');
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const report={status:'RUNNING',version:build.version,run,errors:[],checks:[],scope:'Real Maximum50/1024 local concept and persisted measured encoding. Negative fixtures edit only queued contracts inside this isolated QA SQLite library; no installed model/tokenizer/runtime/weights are edited. No artistic or full-3D claim.'};
let child,browser,page,closing=false;
async function open(){
 child=spawn(path.join(build.delivery_location,build.executable),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 return async(route,body)=>{const r=await fetch(runtime.api_base+route,{method:body?'POST':'GET',headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.clone().text());return r.json();};
}
async function close(){closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});browser=null;page=null;closing=false;}
try{
 let api=await open();
 const project=await api('/api/projects',{name:'Concept conditioning / actual local QA'});
 const asset=await api('/api/assets',{project_id:project.id,name:'Archer Tower / pinned local concept',prompt:'One complete finely detailed stylized archer tower, ivory limestone walls, midnight blue slate roof, timber balcony, carved stone relief, full isolated game asset on a plain neutral studio background.'});
 const body={asset_id:asset.id,request_id:'native-pinned-concept-one',prompt:asset.prompt,quality:'Maximum',seed:43};
 const original=await api('/api/studio/concept',body);report.job_id=original.id;
 assert(original.payload.effective_config.conditioning);const configHash=original.payload.effective_config_hash;
 await page.evaluate(({project,id})=>{localStorage.setItem('afs.project',project);localStorage.setItem('afs.production.selection','job/'+id);location.hash='production';},{project:project.id,id:original.id});await page.reload();
 let ready=false;for(let n=0;n<900;n++){const job=(await api('/api/jobs')).find(j=>j.id===original.id);assert.equal(job.payload.effective_config_hash,configHash);assert(!['FAILED','BLOCKED','CANCELLED'].includes(job.status),JSON.stringify(job));if(job.status==='REVIEW_REQUIRED'){ready=true;break;}await sleep(500);}assert(ready);
 const folder=path.join(library,'jobs',original.id),generation=JSON.parse(fs.readFileSync(path.join(folder,'output/generation.json'),'utf8'));report.actual_generation=generation;
 assert.equal(generation.conditioning_verification.status,'verified');assert.equal(generation.conditioning_verification.identity.code_sha256['sdxl_worker.py'],hash(path.join(root,'engines/sdxl_worker.py')));
 assert.equal(generation.conditioning_verification.identity.code_sha256['concept_conditioning.py'],hash(path.join(root,'engines/concept_conditioning.py')));
 assert.equal(generation.request.steps,50);assert.equal(generation.request.size,1024);assert.deepEqual(generation.dimensions,[1024,1024]);
 const encoding=generation.prompt_encoding;assert.equal(encoding.policy_id,'sdxl_clip_windows_mean_v1');assert.equal(encoding.prompt_sha256,createHash('sha256').update(original.payload.prompt).digest('hex'));assert(encoding.chunks>1);
 for(const direction of ['positive','negative'])for(const name of ['clip_l','clip_g']){const measured=encoding.measured[direction][name];assert.equal(measured.content_tokens_by_window.reduce((a,b)=>a+b,0),measured.content_tokens);assert.equal(measured.content_tokens_by_window.length,encoding.chunks);}
 const output=path.join(folder,'output/concept.png'),pngHash=hash(output);assert.equal(pngHash,generation.output_sha256);
 await page.locator('.production-queue-list').getByRole('button',{name:/Archer Tower \/ pinned local concept/}).click();
 await page.locator('.production-pipeline-link').click();
 await page.locator('.production-pipeline-history').waitFor();await page.screenshot({path:path.join(run,'actual-completed-concept.png')});
 const retry=await api('/api/studio/concept',body);assert.equal(retry.id,original.id);assert.equal((await api('/api/jobs')).length,1);
 await api('/api/production/control',{action:'pause',scope:'all'});
 const stale=await api('/api/studio/concept',{...body,request_id:'native-negative-stale-worker'});
 const changedWeights=await api('/api/studio/concept',{...body,request_id:'native-negative-stale-weights'});
 await close();
 // This deterministic fault modifies only saved expectations, never real files.
 const inject=`import sys,json,sqlite3\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[2])\nfrom engines.quality import fingerprint\nlib=Path(sys.argv[1]).resolve()\nassert lib.is_relative_to(Path(sys.argv[2]).resolve()/'.local/concept-conditioning-native')\nwith sqlite3.connect(lib/'studio.sqlite') as db:\n for identifier,kind in [(sys.argv[3],'worker'),(sys.argv[4],'weights')]:\n  status,raw=db.execute('SELECT status,payload FROM jobs WHERE id=?',(identifier,)).fetchone()\n  assert status=='QUEUED'\n  payload=json.loads(raw);cfg=payload['effective_config']\n  if kind=='worker':cfg['conditioning']['code_sha256']['sdxl_worker.py']='0'*64\n  else:\n   files=cfg['checkpoint']['files'];files[next(iter(files))]='0'*64;cfg['checkpoint']['manifest_hash']=fingerprint(files)\n  payload['effective_config_hash']=fingerprint(cfg)\n  db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),identifier))\n`;
 execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-c',inject,library,root,stale.id,changedWeights.id],{windowsHide:true});
 api=await open();await sleep(1000);assert((await api('/api/jobs')).filter(j=>[stale.id,changedWeights.id].includes(j.id)).every(j=>j.status==='QUEUED'),'GPU work must wait for explicit Resume after restart');
 await api('/api/production/control',{action:'resume',scope:'all'});
 let blocked=false;for(let n=0;n<300;n++){const jobs=await api('/api/jobs');const a=jobs.find(j=>j.id===stale.id),b=jobs.find(j=>j.id===changedWeights.id);if(a.status==='BLOCKED'&&b.status==='BLOCKED'){report.negative_jobs=[a,b];blocked=true;break;}assert(![a.status,b.status].includes('REVIEW_REQUIRED'));await sleep(500);}assert(blocked);
 assert(report.negative_jobs[0].error.includes('identity changed'));assert(!fs.existsSync(path.join(library,'jobs',stale.id,'process.json')));
 const rejected=JSON.parse(fs.readFileSync(path.join(library,'jobs',changedWeights.id,'output/generation.json'),'utf8'));assert.equal(rejected.quality_guard_blocked,true);assert.equal(rejected.status,'BLOCKED_QUALITY_LOCK');assert(!fs.existsSync(path.join(library,'jobs',changedWeights.id,'output/concept.png')));report.actual_weight_guard=rejected;
 assert.equal((await api('/api/jobs')).length,3);assert.equal(hash(output),pngHash);
 const detail=await api('/api/production/assets/'+asset.id);assert.equal(detail.asset.art_review_status,'not_reviewed');assert.equal(detail.artifacts.filter(a=>a.role==='concept').length,1);assert.equal(detail.artifacts.find(a=>a.role==='concept').metadata.generation.prompt_encoding.policy_id,encoding.policy_id);assert.equal(report.errors.length,0);
 await page.evaluate(({project})=>{localStorage.setItem('afs.project',project);location.hash='production';},{project:project.id});await page.reload();
 await page.locator('.production-queue-list').getByRole('button',{name:/Archer Tower \/ pinned local concept/}).click();
 await page.locator('.production-pipeline-strip li[data-state="error"]').first().waitFor({timeout:30000});
 await page.locator('.production-pipeline-link').click();
 const attempt=page.locator('.production-stage').filter({hasText:changedWeights.id});await attempt.locator(':scope > summary').click();
 await attempt.getByRole('alert').filter({hasText:'Concept checkpoint weights changed after admission'}).waitFor();
 await page.screenshot({path:path.join(run,'actual-quality-lock-blocked.png')});
 report.checks.push({name:'real_local_concept_measured_windows_correct_code_identity_idempotency_restart_manual_resume_both_actual_guards_no_extra_PNG_art_not_reviewed',passed:true});report.status='PASS_NATIVE_CONCEPT_CONDITIONING';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{await close();fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
