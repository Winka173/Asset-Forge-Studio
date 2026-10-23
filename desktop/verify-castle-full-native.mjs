import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {createHash} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'..'),run=path.join(root,'.local/castle-full-native',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const config=path.join(run,'config'),library=path.join(run,'Library'),game=path.join(run,'GameAssets');fs.mkdirSync(config,{recursive:true});fs.mkdirSync(game);
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,'0.9.17');
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const reference=path.join(root,'.local/fixtures/ArcherTowerSource.png'),referenceHash=hash(reference);
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,closing=false,api,batchId;
const prompt='tạo cho tôi 1 lâu đài, style giống hình ảnh ref này';
const report={status:'RUNNING',version:build.version,run,prompt,reference_sha256:referenceHash,errors:[],transitions:[],scope:'Real packaged pipeline, short Vietnamese castle prompt with original Archer Tower style reference, new Maximum local concept/geometry/PBR/Blender/QA/GLB. Technical acceptance is independent from artistic/Meshy approval. Isolated Library and game directory.'};
const flush=()=>fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));
async function open(){child=spawn(path.join(build.delivery_location,build.executable),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,AFS_INTENT_ENABLED:'1',WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 api=async(route,body)=>{const r=await fetch(runtime.api_base+route,{method:body?'POST':'GET',headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.clone().text());return r.json();};return runtime;
}
async function close(){closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<2400&&child.exitCode===null;n++)await sleep(500);if(browser)await browser.close().catch(()=>{});browser=null;page=null;closing=false;}
try{
 const runtime=await open();const project=await api('/api/projects',{name:'Runavelle castle / actual native Maximum acceptance',art_bible:JSON.parse(fs.readFileSync(path.join(root,'presets/runavelle.json'),'utf8'))});report.project_id=project.id;
 await api('/api/export-profiles/projects/'+project.id,{preset:'glb_only',output_directory:game,manifest:true});
 const asset=await api('/api/assets',{project_id:project.id,name:'Castle / fresh local Maximum pipeline',prompt});report.asset_id=asset.id;
 const form=new FormData();form.append('file',new Blob([fs.readFileSync(reference)]),'ArcherTowerSource.png');const upload=await fetch(runtime.api_base+'/api/import/reference?project_id='+project.id+'&asset_id='+asset.id,{method:'POST',headers:{'X-AFS-Token':runtime.api_token},body:form});assert(upload.ok,await upload.clone().text());const ref=await upload.json();assert.equal(ref.sha256,referenceHash);
 const input={asset_id:asset.id,request_id:'fresh-native-castle-maximum-0917',quality:'Maximum',engine:'auto',seeds:[43],reference_id:ref.id,reference_usage:'auto'};
 const admission=await api('/api/automation/single',input);batchId=admission.batch_id;report.batch_id=batchId;
 assert.equal((await api('/api/automation/single',input)).batch_id,batchId);
 await page.evaluate(id=>{localStorage.setItem('afs.project',id);location.hash='production';},project.id);await page.reload();await page.locator('.production-queue-list').getByRole('button',{name:/Castle \/ fresh local Maximum pipeline/}).click();
 await page.locator('.production-pipeline-link').click();await page.screenshot({path:path.join(run,'actual-submission.png')});
 const start=Date.now();let complete=false,last='';
 for(let n=0;n<1800;n++){
  const group=await api('/api/batches/'+batchId),item=group.items[0],jobs=(await api('/api/jobs')).filter(j=>j.payload.batch_id===batchId);
  const state=[item.automation?.status,item.automation?.stage,...jobs.map(j=>j.payload.kind+':'+j.status)].join(' / ');
  if(state!==last){last=state;report.transitions.push({seconds:(Date.now()-start)/1000,state});console.log(JSON.stringify(report.transitions.at(-1)));await page.screenshot({path:path.join(run,'stage-'+report.transitions.length+'.png')});}
  report.seconds=(Date.now()-start)/1000;report.item=item;report.jobs=jobs;flush();
  assert(jobs.every(j=>j.payload.kind!=='procedural_geometry'),'Maximum must not use procedural blockout fallback');
  if(['failed','blocked'].includes(item.automation?.status))throw Error('Actual pipeline needs attention: '+JSON.stringify(item.automation));
  if(item.automation?.status==='exported'){complete=true;break;}
  if(n%6===0)console.log(JSON.stringify({status:item.automation?.status,stage:item.automation?.stage,seconds:report.seconds}));
  await sleep(5000);
 }
 assert(complete,'Pipeline did not finish within bounded 150-minute test');
 const detail=await api('/api/production/assets/'+asset.id);report.detail=detail;
 assert.equal(detail.asset.original_prompt,prompt);assert.equal(detail.asset.production_status,'completed');assert.equal(detail.asset.qa_status,'passed');assert.equal(detail.asset.art_review_status,'not_reviewed');
 const concepts=detail.artifacts.filter(a=>a.role==='concept');assert(concepts.length>=1);assert(concepts.every(a=>a.sha256!==referenceHash));
 const inference=report.jobs.filter(j=>j.payload.kind==='inference');assert(inference.length>=1);assert(inference.every(j=>j.payload.effective_config.quality==='Maximum'&&j.payload.effective_config.engine_id==='trellis2_community'));
 const output=report.item.automation.export;assert.equal(output.files.filter(f=>f.name.endsWith('.glb')).length,1);assert(!output.files.some(f=>/\.(fbx|blend|zip)$/.test(f.name)));report.delivery=output;
 for(const file of output.files)assert.equal(hash(path.join(output.export_directory,file.name)),file.sha256);
 await page.waitForFunction(()=>Number(document.querySelector('.production-viewport .viewer')?.dataset.loaded)>0,{timeout:90000});await page.screenshot({path:path.join(run,'actual-final-model.png')});
 const jobsBefore=(await api('/api/jobs')).map(j=>j.id).sort();await close();await open();
 const restored=await api('/api/production/assets/'+asset.id);assert.equal(restored.asset.production_status,'completed');assert.equal(restored.asset.art_review_status,'not_reviewed');assert.deepEqual((await api('/api/jobs')).map(j=>j.id).sort(),jobsBefore);
 for(const file of output.files)assert.equal(hash(path.join(output.export_directory,file.name)),file.sha256);assert.equal(hash(reference),referenceHash);assert.equal(report.errors.length,0);
 report.status='PASS_NATIVE_FRESH_CASTLE_TECHNICAL_DELIVERY_ART_NOT_REVIEWED';
}catch(error){report.status='FAILED_OR_NEEDS_ATTENTION';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});if(api&&batchId)await api('/api/batches/'+batchId+'/control',{action:'pause'}).catch(()=>{});process.exitCode=1;}
finally{await close();flush();console.log(JSON.stringify({status:report.status,run,error:report.error}));}
