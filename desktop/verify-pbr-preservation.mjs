// Real retained neural source -> packaged CPU Blender -> PBR QA -> GLB delivery.
// The two CPU processing stages are real; this does not rerun AI or approve art.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';

const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/pbr-preservation-native',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const config=path.join(run,'config'),library=path.join(run,'Library');
fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));
assert.equal(build.version,'0.9.15');
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const validator=createHash('sha256');
for(const name of ['pbr_preservation.py','inspection.py','texture_diagnostics.py']){validator.update(name);validator.update(fs.readFileSync(path.join(root,'apps/api',name)));}
const expectedValidator=validator.digest('hex');
const sources={tower:path.join(root,'.local/native-checkpoint-real/20261022T124320Z/Library/jobs/770b27a74afa439998bc51e9dd320c70/output/raw.glb'),
 castle:path.join(root,'.local/castle-quality-route/20261022T132736Z/Library/jobs/5eff3892f4154fe8a1091ce5d981cb4d/output/raw.glb')};
const hashes=Object.fromEntries(Object.entries(sources).map(([name,file])=>[name,hash(file)]));
const report={status:'RUNNING',version:build.version,run,checks:[],errors:[],sources,hashes,expected_validator_sha256:expectedValidator,results:[],
 scope:'Two retained neural sources, actual current packaged CPU Blender stages and technical delivery. No AI rerun, UV/shader/render equivalence or artistic acceptance.'};
let browser,page,child,closing=false;
async function open(){
 child=spawn(path.join(build.delivery_location,build.executable),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);
 page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});
 await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 return async(route,body)=>{const r=await fetch(runtime.api_base+route,{method:body?'POST':'GET',headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.clone().text());return r.json();};
}
async function close(){
 closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});
 if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);
 if(browser)await browser.close().catch(()=>{});browser=null;page=null;closing=false;
}
try{
 let api=await open();
 const project=await api('/api/projects',{name:'Retained neural PBR / native backend acceptance'});report.project_id=project.id;
 for(const [name,file] of Object.entries(sources)){
  const asset=await api('/api/assets',{project_id:project.id,name:`Actual ${name} / PBR preservation`,prompt:'Retained real neural output. No new diffusion. Artistic review remains separate.'});
  const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
  const form=new FormData();form.append('file',new Blob([fs.readFileSync(file)]),`${name}.glb`);
  const response=await fetch(runtime.api_base+`/api/import/candidate?project_id=${project.id}&asset_id=${asset.id}`,{method:'POST',headers:{'X-AFS-Token':runtime.api_token},body:form});
  assert(response.ok,await response.clone().text());const original=await response.json();assert.equal(original.sha256,hashes[name]);
  const job=await api('/api/jobs/blender',{artifact_id:original.id,render:false,export_fbx:false});
  let completed=false;for(let n=0;n<800;n++){const current=(await api('/api/jobs')).find(j=>j.id===job.id);assert(!['FAILED','BLOCKED','CANCELLED'].includes(current.status),JSON.stringify(current));if(current.status==='REVIEW_REQUIRED'){completed=true;break;}await sleep(1000);}assert(completed);
  const detail=await api('/api/production/assets/'+asset.id),processed=detail.artifacts.find(a=>a.metadata.job_id===job.id&&a.metadata.stage==='blender_processed');assert(processed);
  const qa=processed.metadata.pbr_preservation;assert.equal(qa.status,'Pass');assert.equal(qa.validator_sha256,expectedValidator);assert(Object.values(qa.checks).every(Boolean));assert.equal(qa.source_sha256,original.sha256);assert.equal(qa.target_sha256,processed.sha256);assert.equal(qa.artistic_quality,'NotEvaluated');assert.equal(qa.sampler_fidelity,'NotEvaluated');
  assert.equal(detail.stages.find(j=>j.id===job.id).qa.pbr_preservation.status,'Pass');
  const manifest=JSON.parse(fs.readFileSync(path.join(library,'jobs',job.id,'manifest.json'),'utf8'));assert.equal(manifest.checks.core_pbr_preservation,'Pass');
  const delivery=await api('/api/export-profiles/assets/'+asset.id,{artifact_id:processed.id});assert.equal(delivery.settings.preset,'glb_only');assert.equal(delivery.files.filter(f=>f.kind==='glb').length,1);
  for(const f of delivery.files)assert.equal(hash(path.join(delivery.export_directory,f.name)),f.sha256);
  assert.equal(detail.asset.art_review_status,'not_reviewed');assert.equal(hash(file),hashes[name]);
  report.results.push({name,asset_id:asset.id,job_id:job.id,artifact_id:processed.id,qa,delivery});
 }
 await page.evaluate(id=>{localStorage.setItem('afs.project',id);localStorage.setItem('afs.inspector.view','preview');},project.id);await page.reload();await page.getByRole('link',{name:'Library',exact:true}).click();
 await page.getByRole('button',{name:'Actual castle / PBR preservation',exact:true}).click();
 await page.waitForFunction(()=>Number(document.querySelector('.library-detail-viewport .viewer')?.dataset.loaded)>0&&Number(document.querySelector('.library-detail-viewport .viewer')?.dataset.textures)>0);
 await page.screenshot({path:path.join(run,'actual-castle-processed-delivery.png')});
 await close();api=await open();
 assert.equal((await api('/api/jobs')).length,2);
 for(const result of report.results){const detail=await api('/api/production/assets/'+result.asset_id);assert.equal(detail.artifacts.find(a=>a.id===result.artifact_id).metadata.pbr_preservation.status,'Pass');assert(detail.exports.some(e=>e.id===result.delivery.id&&e.artifact_id===result.artifact_id));for(const f of result.delivery.files)assert.equal(hash(path.join(result.delivery.export_directory,f.name)),f.sha256);assert.equal(detail.asset.art_review_status,'not_reviewed');assert.equal(hash(sources[result.name]),hashes[result.name]);}
 assert.equal(report.errors.length,0);
 report.checks.push({name:'two_real_CPU_Blender_jobs_PBR_hashbound_measurements_GLBonIy_delivery_viewer_restart_no_extra_inference_sources_preserved_art_separate',passed:true});
 report.status='PASS_NATIVE_PBR_PRESERVATION';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{await close();fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
