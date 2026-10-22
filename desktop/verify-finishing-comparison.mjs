// Actual retained GLBs in the packaged shared-camera viewer; no artistic approval.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {createHash} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'..'),run=path.join(root,'.local/finishing-comparison-native',new Date().toISOString().replaceAll(/[:.]/g,'-')),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
const files={golden:process.env.AFS_BASELINE_GLB||path.join(root,'.local/native-checkpoint-real/20261022T124320Z/Library/jobs/770b27a74afa439998bc51e9dd320c70/output/raw.glb'),candidate:process.env.AFS_COMPARISON_GLB||path.join(root,'.local/projection-finishing/20261022T135129Z/output/raw.glb')};
const hashes=Object.fromEntries(Object.entries(files).map(([k,p])=>[k,createHash('sha256').update(fs.readFileSync(p)).digest('hex')]));
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,process.env.AFS_EXPECTED_VERSION||'0.9.6');
const exe=path.join(build.delivery_location,build.executable),server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page,child,closing=false;
const report={status:'RUNNING',version:build.version,run,files,hashes,errors:[],checks:[],scope:'Retained native source, unchanged original output and experimental derived finishing; actual shared-camera viewer, not Meshy or artistic approval.'};
try{
 child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(90000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const call=async(route,options={})=>{const r=await fetch(runtime.api_base+route,{...options,headers:{'X-AFS-Token':runtime.api_token,...options.headers}});assert(r.ok,await r.clone().text());return r.json();};
 const project=await call('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:process.env.AFS_COMPARISON_NAME||'Finishing fidelity A/B / retained tower'})});
 report.artifacts={};
 for(const role of ['golden','candidate']){const body=new FormData();body.append('file',new Blob([fs.readFileSync(files[role])]),role==='golden'?'Baseline-original-finishing.glb':process.env.AFS_COMPARISON_FILE||'Experimental-derived-finishing.glb');const artifact=await call('/api/import/'+role+'?project_id='+project.id,{method:'POST',body});assert.equal(artifact.sha256,hashes[role]);report.artifacts[role]=artifact;}
 await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.getByRole('link',{name:'Compare',exact:true}).click();
 await page.waitForFunction(()=>Number(document.querySelector('.quality-lab #compare .viewer')?.dataset.loaded)===2&&Number(document.querySelector('.quality-lab #compare .viewer')?.dataset.textures)>0);
 assert((await page.locator('.model-labels').innerText()).includes('REFERENCE / BASELINE MODEL'));assert(!(await page.locator('.model-labels').innerText()).includes('MESHY'));
 for(const view of ['three_quarter','front','back','side']){await page.getByRole('combobox',{name:'Góc camera',exact:true}).click();await page.getByRole('option',{name:view,exact:true}).click();await page.locator('#compare .viewer').scrollIntoViewIfNeeded();await sleep(400);await page.screenshot({path:path.join(run,view+'.png')});}
 if(process.env.AFS_SURFACE_CHECK==='1'){
  const panels=page.getByLabel('Measured triangle and shading diagnostics',{exact:true});assert.equal(await panels.count(),2);
  for(let i=0;i<2;i++){const role=i===0?'golden':'candidate',panel=panels.nth(i),expected=report.artifacts[role].metadata.surface_diagnostics;assert(expected);await panel.locator('summary').click();assert((await panel.innerText()).includes(expected.totals.very_thin_triangles.toLocaleString('en-US')));assert((await panel.innerText()).includes(expected.faces_opposing_mean_vertex_normal.toLocaleString('en-US')));}
  await panels.first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(run,'actual-surface-diagnostics.png')});report.checks.push({name:'actual_both_GLB_surface_counts_match_import_measurements',passed:true});
 }
 assert.equal((await call('/api/jobs')).length,0);assert.equal(report.errors.length,0);
 for(const role of ['golden','candidate'])assert.equal(createHash('sha256').update(fs.readFileSync(files[role])).digest('hex'),hashes[role]);
 report.checks.push({name:'real_reference_and_candidate_same_camera_textured_no_false_meshy_label_no_inference_sources_preserved',passed:true});report.status='PASS_NATIVE_REAL_FINISHING_AB';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
