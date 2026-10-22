// Actual retained model and measured metadata in the packaged Library/Production.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'),source=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/lod_quality_real_v095.json'),'utf8'));
const run=path.join(root,'.local/lod-quality-native',new Date().toISOString().replaceAll(/[:.]/g,'-')),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(source.run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,'0.9.5');
const exe=path.join(build.delivery_location,build.executable),server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page,child,closing=false;
const report={status:'RUNNING',version:build.version,run,errors:[],checks:[],scope:'Measured LOD surface evidence for a retained real tower; no new inference, artistic score or global worst-case/silhouette claim.'};
try{
 child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const get=async route=>{const r=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token}});assert(r.ok);return r.json();};
 const before=await get('/api/jobs');await page.evaluate(id=>localStorage.setItem('afs.project',id),source.project_id);await page.reload();await page.getByRole('link',{name:'Library',exact:true}).click();await page.locator('.library-card-open').filter({hasText:'Archer Tower / measured LOD quality'}).first().click();
 await page.waitForFunction(()=>Number(document.querySelector('.library-detail-viewport .viewer')?.dataset.loaded)>0);
 let evidence=page.getByLabel('Measured LOD geometry retention',{exact:true});await evidence.locator('summary').click();await evidence.scrollIntoViewIfNeeded();assert.equal(await evidence.locator('tbody tr').count(),3);
 for(const row of source.lods){const tr=evidence.locator('tbody tr').filter({hasText:'LOD '+row.level});assert((await tr.innerText()).includes(row.surface_error.target_triangles.toLocaleString('en-US')));assert((await tr.innerText()).includes((row.surface_error.symmetric_p95_relative_diagonal*100).toFixed(3)+'%'));}
 await page.screenshot({path:path.join(run,'library-measured-lod-table.png')});
 const padding=await evidence.evaluate(e=>parseFloat(getComputedStyle(e).paddingLeft));assert(padding>=18,'LOD card must retain actual horizontal padding');
 await page.getByRole('button',{name:'Show in Production',exact:true}).click();await page.getByLabel('Measured LOD geometry retention',{exact:true}).waitFor();await page.waitForFunction(()=>Number(document.querySelector('.production-viewport .viewer')?.dataset.loaded)>0);evidence=page.getByLabel('Measured LOD geometry retention',{exact:true});await evidence.locator('summary').click();await evidence.scrollIntoViewIfNeeded();assert.equal(await evidence.locator('tbody tr').count(),3);await page.screenshot({path:path.join(run,'production-measured-lod-table.png')});
 await page.reload();await page.getByLabel('Measured LOD geometry retention',{exact:true}).waitFor();assert.equal((await get('/api/jobs')).length,before.length);assert.equal(report.errors.length,0);
 report.checks.push({name:'actual_library_and_production_LOD_measurements_match_real_report_and_survive_refresh_no_jobs',passed:true,asset_id:source.asset_id,artifact_id:source.artifact.id,levels:source.lods.map(l=>({level:l.level,measurement:l.surface_error}))});report.status='PASS_NATIVE_MEASURED_LOD_EVIDENCE';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
