// Actual packaged Windows UI -> shared GPU scheduler -> Unity Editor -> native files.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn,spawnSync} from 'node:child_process';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const baseline=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_inference.json')));
const run=baseline.run;const library=path.join(run,'Library');const errors=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,session,closing=false;
const report={status:'RUNNING',branch:'feature/universal-expansion-v2-reviewed',scope:'Real packaged native UI and isolated Unity 6000.4.8f1 Built-in import/reopen/GPU/package; no production game changes',checks:[],errors,meshy_parity:'NOT_TESTED',human_quality_approval:'NOT_GIVEN'};
async function launch(){
 child=spawn(path.join(root,'dist/windows/latest/Asset Forge Studio.exe'),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:path.join(run,'config'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port=19390'},stdio:'ignore',windowsHide:false});
 closing=false;for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:19390');break;}catch{await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.on('console',m=>{if(m.type()==='error'&&!closing)errors.push(m.text().replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]'));});page.on('pageerror',e=>errors.push(e.message));
 await page.locator('.studio-sidebar').waitFor({timeout:180000});session=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
}
async function api(route,body){const r=await fetch(session.api_base+route,{headers:{'X-AFS-Token':session.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});assert(r.ok,`API ${route}: ${r.status}`);return r.json();}
async function close(){closing=true;await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<180&&child.exitCode===null;n++)await sleep(500);assert.notEqual(child.exitCode,null);await browser.close().catch(()=>{});browser=null;}
async function openAsset(id){await page.evaluate(id=>{location.hash=`create/${id}`;},id);await page.reload();await page.locator('.unity-import-panel summary').waitFor({timeout:120000});await page.locator('.unity-import-panel summary').click();}
try{
 await launch();report.version=session.version;
 const snapshot=await api('/api/studio?project_id=runavelle');const asset=snapshot.assets.find(a=>a.name==='Archer Tower Maximum Single QA');assert(asset);
 const source=asset.versions.findLast(v=>v.metadata.stage==='blender_processed');assert(source);const before=(await api('/api/jobs')).length;
 await openAsset(asset.id);
 const submitted=page.waitForResponse(r=>r.url().endsWith(`/api/platform/assets/${asset.id}/unity-import`)&&r.request().method()==='POST',{timeout:180000});
 await page.getByRole('button',{name:/^(Revalidate|Validate) in Unity$/}).click();
 const response=await submitted;assert(response.ok(),await response.text());const job=await response.json();
 const repeated=await api(`/api/platform/assets/${asset.id}/unity-import`,JSON.parse(response.request().postData()));assert.equal(repeated.id,job.id);
 await page.reload();await page.locator('.studio-sidebar').waitFor();assert.equal((await api('/api/jobs')).length,before+1);
 const began=Date.now();let final;let lockChecked=false;
 for(;;){final=(await api('/api/jobs')).find(j=>j.id===job.id);assert(final);
  if(final.status==='POSTPROCESSING'&&!lockChecked){
   const proof=spawnSync(path.join(root,'.venv/Scripts/python.exe'),['-c',"from apps.api.jobs import exclusive_worker_lock\ntry:\n with exclusive_worker_lock(): print('UNEXPECTED_FREE_GPU_SLOT')\nexcept OSError: print('GPU_SLOT_BUSY_CONFIRMED')"],{cwd:root,encoding:'utf8',windowsHide:true});
   assert.equal(proof.status,0);assert(proof.stdout.includes('GPU_SLOT_BUSY_CONFIRMED'));lockChecked=true;
  }
  if(['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(final.status))break;
  assert(Date.now()-began<900000,'Actual Unity validation timed out');await sleep(5000);
 }
 assert.equal(final.status,'REVIEW_REQUIRED',final.error);assert(lockChecked,'GPU lock was not observed during actual Editor processing');
 const folder=path.join(library,'jobs',job.id);const native=JSON.parse(fs.readFileSync(path.join(folder,'manifest.json')));assert.equal(native.status,'PASS_EDITOR_VALIDATION');
 assert(native.reports.every(r=>r.checks_passed&&r.unity_version==='6000.4.8f1'));
 const files=await api(`/api/jobs/${job.id}/files`);assert(!files.some(f=>f.name.startsWith('editor_project/Library/')));
 const pkg=files.find(f=>f.name==='output/AFS_Asset.unitypackage');assert(pkg&&pkg.bytes>1000000);
 const range=await fetch(session.api_base+pkg.url,{headers:{'X-AFS-Token':session.api_token,Range:'bytes=0-1023'}});assert.equal(range.status,206);const header=new Uint8Array(await range.arrayBuffer());assert.equal(header[0],31);assert.equal(header[1],139);
 const immutable=crypto.createHash('sha256').update(fs.readFileSync(path.join(library,source.relative_path))).digest('hex');assert.equal(immutable,source.sha256);
 const manifest=await api(`/api/platform/assets/${asset.id}/manifest`);assert(manifest.import_tests.some(t=>t.job_id===job.id&&t.status==='PASS_EDITOR_VALIDATION'));
 report.job_id=job.id;report.job_path=folder;report.native_report=native;report.resources=JSON.parse(fs.readFileSync(path.join(folder,'resources.json')));delete report.resources.samples;
 report.package={bytes:pkg.bytes,sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(folder,'output/AFS_Asset.unitypackage'))).digest('hex')};
 report.checks.push({name:'native_ui_import_shared_gpu_lock_idempotency_and_refresh',passed:true},{name:'actual_serialized_prefab_scene_lods_materials_collider_and_cold_reopen',passed:true},{name:'actual_package_http_range_and_unchanged_source_hash',passed:true});
 await openAsset(asset.id);await page.locator('.unity-import-panel img').first().waitFor({timeout:120000});await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0&&Number(document.querySelector('.viewer')?.dataset.textures)>0,null,{timeout:120000});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(folder,'native-unity-result.png'),fullPage:true});
 await close();await launch();const saved=(await api('/api/jobs')).find(j=>j.id===job.id);assert.equal(saved.status,'REVIEW_REQUIRED');assert.equal((await api('/api/jobs')).length,before+1);
 await openAsset(asset.id);await page.locator('.unity-import-panel img').first().waitFor({timeout:120000});await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0&&Number(document.querySelector('.viewer')?.dataset.textures)>0,null,{timeout:120000});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(folder,'native-unity-reopened.png'),fullPage:true});
 report.checks.push({name:'native_relaunch_restores_import_job_and_actual_previews_without_duplicate_work',passed:true});await close();assert.equal(errors.length,0,errors.join('\n'));report.status='PASS_REAL_NATIVE_UNITY_SLICE';
}catch(e){report.status='FAILED';report.failure=String(e).replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]');process.exitCode=1;}
finally{fs.writeFileSync(path.join(root,'docs/evidence/universal_unity_native.json'),JSON.stringify(report,null,2));if(browser)await browser.close().catch(()=>{});console.log(JSON.stringify({status:report.status,job:report.job_id,failure:report.failure}));}
