// Actual million-triangle neural GLB import, inspection, viewer and native restart.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';
import assert from 'node:assert/strict';import {spawn} from 'node:child_process';import {createHash} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/missing-normals-native',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const config=path.join(run,'config'),library=path.join(run,'Library');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^\uFEFF/,''));assert.equal(build.version,process.env.AFS_EXPECTED_VERSION||'0.9.17');
const source=path.join(root,'data/research_castle_geometry/20261023T021252Z/trellis_v1-42/output/raw.glb');
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');const sourceHash=hash(source);
const contents=fs.readFileSync(source),doc=JSON.parse(contents.subarray(20,20+contents.readUInt32LE(12)).toString());
assert(doc.meshes.every(m=>m.primitives.every(p=>!('NORMAL' in p.attributes))));
const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,closing=false;
const report={status:'RUNNING',version:build.version,run,source,source_sha256:sourceHash,errors:[],scope:'Real retained TRELLIS v1 neural castle without NORMAL attributes; packaged API import, selected QA, visible GLB and restart. No new inference, texture/PBR, quality approval or export claim.'};
async function open(){
 child=spawn(path.join(build.delivery_location,build.executable),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{assert.equal(child.exitCode,null);await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];page.setDefaultTimeout(60000);page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});
 const runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
 const api=async(route,body)=>{const r=await fetch(runtime.api_base+route,{method:body?'POST':'GET',signal:AbortSignal.timeout(30000),headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.clone().text());return r.json();};return {runtime,api};
}
async function close(){closing=true;if(page)await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});if(child)for(let n=0;n<180&&child.exitCode===null;n++)await sleep(200);if(browser)await browser.close().catch(()=>{});browser=null;page=null;closing=false;}
async function showModel(project){
 await page.evaluate(id=>localStorage.setItem('afs.project',id),project);await page.reload();
 await page.getByRole('link',{name:'Library',exact:true}).click();
 const back=page.getByRole('button',{name:'← Back to Library',exact:true});if(await back.isVisible())await back.click();
 await page.locator('.library-card-open').filter({hasText:'Castle / real missing-normal inspection'}).first().click();
 await page.waitForFunction(()=>Number(document.querySelector('.library-detail-viewport .viewer')?.dataset.loaded)>0);
 const panel=page.getByLabel('Measured triangle and shading diagnostics',{exact:true});if(!await panel.evaluate(e=>e.open))await panel.locator('summary').click();
 assert((await panel.innerText()).includes('Finite vertex normals'));assert((await panel.innerText()).includes('Yes'));await panel.scrollIntoViewIfNeeded();
}
try{
 let {runtime,api}=await open();const project=await api('/api/projects',{name:'Missing normals / real geometry QA'});
 const asset=await api('/api/assets',{project_id:project.id,name:'Castle / real missing-normal inspection',prompt:'Inspect retained neural castle; preserve original geometry and no artistic approval.'});
 const form=new FormData();form.append('file',new Blob([contents]),'actual-neural-castle-no-normals.glb');const start=performance.now();
 const response=await fetch(runtime.api_base+'/api/import/candidate?project_id='+project.id+'&asset_id='+asset.id,{method:'POST',signal:AbortSignal.timeout(30000),headers:{'X-AFS-Token':runtime.api_token},body:form});assert(response.ok,await response.clone().text());
 const imported=await response.json();report.import_seconds=(performance.now()-start)/1000;report.asset_id=asset.id;report.artifact_id=imported.id;
 const diagnostics=imported.metadata.surface_diagnostics;report.diagnostics=diagnostics;
 assert.equal(diagnostics.totals.triangles,1269640);assert.equal(diagnostics.validator_sha256,hash(path.join(root,'apps/api/surface_diagnostics.py')));
 assert(diagnostics.meshes.every(m=>m.vertex_normals_source.includes('derived angle-weighted')));assert(diagnostics.all_vertex_normals_finite);assert.equal(imported.sha256,sourceHash);
 const inspectStart=performance.now();const inspected=await api('/api/library/bulk',{asset_ids:[asset.id],artifact_id:imported.id,action:'inspect'});assert.equal(inspected.errors.length,0);assert.equal(inspected.completed.length,1);report.reinspection_seconds=(performance.now()-inspectStart)/1000;
 assert.equal(inspected.completed[0].report.surface_diagnostics.validator_sha256,diagnostics.validator_sha256);
 await showModel(project.id);await page.screenshot({path:path.join(run,'actual-million-triangle-viewer.png')});
 assert.equal((await api('/api/jobs')).length,0);await close();({api}=await open());
 const detail=await api('/api/production/assets/'+asset.id);assert.equal(detail.asset.art_review_status,'not_reviewed');
 const reopened=detail.artifacts.find(a=>a.id===imported.id);assert(reopened.metadata.inspection_at);assert.equal(reopened.sha256,sourceHash);assert.equal(reopened.metadata.triangles,1269640);
 assert.equal(reopened.metadata.surface_diagnostics.validator_sha256,diagnostics.validator_sha256);
 assert.equal(detail.artifacts.filter(a=>a.role==='candidate').length,1);assert.equal((await api('/api/jobs')).length,0);
 await showModel(project.id);await page.screenshot({path:path.join(run,'actual-reopened-neural-castle.png')});
 assert.equal(hash(source),sourceHash);assert.equal(report.errors.length,0);report.status='PASS_NATIVE_REAL_MISSING_NORMALS';
}catch(error){report.status='FAILED';report.error=String(error);if(page)await page.screenshot({path:path.join(run,'failure.png')}).catch(()=>{});process.exitCode=1;}
finally{await close();fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
