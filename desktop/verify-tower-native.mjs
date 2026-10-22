// Load the freshly generated real tower in the packaged viewer. No inference mocks.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'),replay=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/tower_replay_real.json'),'utf8'));
const run=path.join(root,'.local/tower-native',new Date().toISOString().replaceAll(/[:.]/g,'-')),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(replay.run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,'')),exe=path.join(build.delivery_location,build.executable);
const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page,child,closing=false;
const report={status:'RUNNING',version:build.version,executable:exe,run,errors:[],checks:[],scope:'Actual fresh tower GLB loaded in packaged Three.js viewer. Native source array parity is recorded separately; no art/Meshy equivalence claim.'};
try{
 child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser,'Packaged WebView missing');page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});
 await page.locator('.studio-sidebar').waitFor({timeout:180000});const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const get=async route=>{const r=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token}});assert(r.ok);return r.json();};
 const jobsBefore=await get('/api/jobs');assert(jobsBefore.every(j=>['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'].includes(j.status)));
 await page.evaluate(id=>localStorage.setItem('afs.project',id),replay.artifact.project_id);await page.reload();await page.getByRole('link',{name:'Library',exact:true}).click();
 await page.locator('.library-card-open').filter({hasText:'Archer Tower / preserved source'}).first().click();
 await page.waitForFunction(()=>{const viewer=document.querySelector('.library-detail-viewport .viewer');return Number(viewer?.dataset.loaded)>0&&Number(viewer?.dataset.textures)>0;},{timeout:90000});
 await page.screenshot({path:path.join(run,'fresh-tower-packaged-viewer.png'),fullPage:true});
 const actual=await page.locator('.library-detail-viewport .viewer').evaluate(e=>({loaded:e.dataset.loaded,textures:e.dataset.textures}));
 assert.equal((await get('/api/jobs')).length,jobsBefore.length);assert.equal(report.errors.length,0);
 report.checks.push({name:'fresh_actual_tower_GLb_visible_with_textures_no_new_jobs',passed:true,artifact_id:replay.artifact.id,sha256:replay.artifact.sha256,actual});
 report.status='PASS_NATIVE_FRESH_TOWER_VIEWER';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
finally{
 closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});
 if(child)for(let n=0;n<150&&child.exitCode===null;n++)await sleep(200);
 if(browser)await browser.close().catch(()=>{});
 fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));
}
