// Packaged UI + actual retained GLB export + real bounded CUDA allocation.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import crypto from 'node:crypto';import {spawn} from 'node:child_process';
import {openGpuPopover} from './ui-helpers.mjs';
const root=path.resolve(import.meta.dirname,'..'),replay=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/tower_replay_real.json'),'utf8'));
const run=path.join(root,'.local/workspace-polish-native',new Date().toISOString().replaceAll(/[:.]/g,'-')),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(replay.run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,'')),exe=path.join(build.delivery_location,build.executable);
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page,child,closing=false,load;
const report={status:'RUNNING',version:build.version,run,errors:[],checks:[],scope:'Native WebView UI with actual historical test-library GLB. GPU telemetry change uses a real 512 MiB allocation under the shared resource lock, not inference or an art quality test.'};
try{
 child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const get=async route=>{const r=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token}});assert(r.ok);return r.json();};
 const jobsBefore=await get('/api/jobs');
 await page.evaluate(id=>localStorage.setItem('afs.project',id),replay.artifact.project_id);await page.reload();
 await openGpuPopover(page);const meter=page.getByLabel('Live GPU measurements',{exact:true});await meter.waitFor();const firstSample=await meter.getAttribute('data-sampled-at');await page.waitForFunction(t=>document.querySelector('.gpu-live-details')?.dataset.sampledAt!==t,firstSample);
 const baseline=Number(await meter.getAttribute('data-vram-mib'));let log='';
 load=spawn(path.join(root,'.venv/Scripts/python.exe'),['-u','scripts/verify_gpu_live_load.py'],{cwd:root,stdio:['ignore','pipe','pipe'],windowsHide:true});load.stdout.on('data',b=>log+=String(b));load.stderr.on('data',b=>log+=String(b));
 for(let n=0;n<90&&!log.includes('REAL_CUDA_ALLOCATION_READY');n++){assert.equal(load.exitCode,null,log);await sleep(500);}assert(log.includes('REAL_CUDA_ALLOCATION_READY'),log);
 await page.waitForFunction(v=>Number(document.querySelector('.gpu-live-details')?.dataset.vramMib)>=v+256,baseline,{timeout:12000});
 const actual=await meter.evaluate(e=>({...e.dataset,text:e.textContent}));await page.screenshot({path:path.join(run,'live-vram.png'),fullPage:false});
 for(let n=0;n<60&&load.exitCode===null;n++)await sleep(500);assert.equal(load.exitCode,0,log);
 report.checks.push({name:'real_uncached_GPU_samples_and_real_allocation_visible',passed:true,baseline_mib:baseline,actual,scope:'Whole GPU current usage; sampled session peak is not an exact per-job maximum.'});
 await page.getByRole('button',{name:'Collapse sidebar',exact:true}).click();await page.waitForFunction(()=>Math.round(document.querySelector('.studio-sidebar').getBoundingClientRect().width)===76);assert.equal(Math.round(await page.locator('.studio-sidebar').evaluate(e=>e.getBoundingClientRect().width)),76);
 assert.equal(await page.locator('.production-secondary-label').isVisible(),false);await page.reload();await page.getByRole('button',{name:'Expand sidebar',exact:true}).waitFor();
 await page.screenshot({path:path.join(run,'collapsed-sidebar.png'),fullPage:false});await page.getByRole('button',{name:'Expand sidebar',exact:true}).click();await page.waitForFunction(()=>{const w=document.querySelector('.studio-sidebar').getBoundingClientRect().width;return w>=165&&w<=218;});
 report.checks.push({name:'sidebar_76px_icons_only_persists_refresh',passed:true});
 await page.getByRole('link',{name:'Library',exact:true}).click();await page.locator('.library-card-open').filter({hasText:'Archer Tower / preserved source'}).first().click();
 await page.waitForFunction(()=>Number(document.querySelector('.library-detail-viewport .viewer')?.dataset.loaded)>0);
 const selectedBefore=await get('/api/production/assets/'+replay.artifact.asset_id);
 const exportModel=async scope=>{
   const response=page.waitForResponse(r=>r.url().includes('/api/export-profiles/assets/')&&r.request().method()==='POST');await page.getByRole('button',{name:'Export model',exact:true}).click();const r=await response;assert(r.ok(),await r.text());const result=await r.json();assert(result.files.length>0);
   for(const f of result.files){const bytes=fs.readFileSync(path.join(result.export_directory,f.name));assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),f.sha256);if(f.name.endsWith('.glb'))assert.equal(bytes.toString('ascii',0,4),'glTF');}
   assert.equal(result.artifact_id,selectedBefore.artifacts.filter(a=>a.role==='candidate'&&a.metadata.stage==='blender_processed').at(-1).id);
   report.checks.push({name:scope+'_visible_selected_version_export_actual_hashes_no_inference',passed:true,export:result});
 };
 await exportModel('library');await page.screenshot({path:path.join(run,'library-export.png'),fullPage:false});
 await page.getByRole('button',{name:/^(Review later|Marked for later)$/}).click();await page.locator('.afs-toast').waitFor();await page.screenshot({path:path.join(run,'saved-action-toast.png')});assert.equal(await page.locator('.asset-management-notice').count(),0);await page.getByRole('button',{name:'Dismiss notification',exact:true}).click();await page.locator('.afs-toast').waitFor({state:'detached'});
 report.checks.push({name:'real_saved_review_marker_uses_dismissible_portal_toast',passed:true});
 await page.getByRole('button',{name:'Show in Production',exact:true}).click();await page.getByRole('button',{name:'Export model',exact:true}).waitFor();await exportModel('production');await page.screenshot({path:path.join(run,'production-export.png'),fullPage:false});
 assert.equal((await get('/api/jobs')).length,jobsBefore.length);assert.equal((await get('/api/production/assets/'+replay.artifact.asset_id)).asset.published_artifact_id,selectedBefore.asset.published_artifact_id);assert.equal(report.errors.length,0);report.status='PASS_NATIVE_WORKSPACE_POLISH';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png'),fullPage:false}).catch(()=>{});process.exitCode=1;}
finally{closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<150&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
