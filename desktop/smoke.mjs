// Actual Windows executable/WebView2 automation, not a browser preview or mock IPC.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
const executable=process.env.AFS_SMOKE_EXE || path.join(root,'dist/windows/latest/Asset Forge Studio.exe');
if(!fs.existsSync(executable))throw Error('Build a Windows executable before desktop:smoke');
const stamp=new Date().toISOString().replaceAll(/[:.]/g,'-');
const run=path.join(root,'.local/desktop-smoke',stamp);fs.mkdirSync(run,{recursive:true});
const config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
const library=path.join(run,'Library');
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library,blender:null,setup_complete:false},null,2));
const report={version:JSON.parse(fs.readFileSync(path.join(root,'package.json'))).version,executable,run_path:run,purpose:'Actual native application smoke; imported existing local model, no AI inference or art approval',checks:[],errors:[],status:'RUNNING'};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const value=server.address().port;await new Promise(resolve=>server.close(resolve));return value;}
let child,browser,page;
const cdp=await port();
function launch(){return spawn(executable,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${cdp}`},stdio:'ignore',windowsHide:false});}
async function connect(){for(let count=0;count<180;count++){if(child.exitCode!==null)throw Error(`Desktop exited before UI ready (${child.exitCode})`);try{return await chromium.connectOverCDP(`http://127.0.0.1:${cdp}`);}catch{await sleep(1000);}}throw Error('WebView2 CDP startup timed out');}
async function session(){return page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));}
async function api(route,body){const runtime=await session();const response=await fetch(runtime.api_base+route,{headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});if(!response.ok)throw Error(`Native API ${route.split('?')[0]} returned ${response.status}`);return response.json();}
async function close(){const runtime=await session();await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});for(let count=0;count<100&&child.exitCode===null;count++)await sleep(200);if(child.exitCode===null)throw Error('Desktop failed to shut down cleanly');for(let count=0;count<30;count++){try{await fetch(runtime.api_base+'/api/desktop/health',{headers:{'X-AFS-Token':runtime.api_token}});await sleep(200);}catch{return;}}throw Error('Owned backend remained alive after desktop exit');}
try{
  child=launch();browser=await connect();page=browser.contexts()[0].pages()[0] || await browser.contexts()[0].waitForEvent('page');page.on('console',m=>{if(m.type()==='error')report.errors.push(m.text().replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]'));});page.on('pageerror',e=>report.errors.push(e.message.replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]')));
  await page.getByRole('button',{name:'Open studio',exact:true}).waitFor({timeout:180000});
  await page.screenshot({path:path.join(run,'first-run.png')});await page.getByRole('button',{name:'Open studio',exact:true}).click();
  await page.locator('.studio-sidebar').waitFor({timeout:30000});
  const first=await session();const health=await api('/api/desktop/health');
  if(!first.api_base?.startsWith('http://127.0.0.1:'))throw Error('Backend was not loopback-only');
  const unauthorized=await fetch(first.api_base+'/api/studio');if(![401,403].includes(unauthorized.status))throw Error('Unauthenticated API access was not denied');
  report.checks.push({name:'native_window_and_packaged_backend',passed:true,page_url:page.url(),native_pid:child.pid,backend_pid:health.pid,library:health.data_path,unauthorized_status:unauthorized.status});
  const duplicate=launch();await sleep(2000);if((await api('/api/desktop/health')).pid!==health.pid)throw Error('Duplicate launch started a second backend');report.checks.push({name:'single_instance_backend',passed:true,duplicate_exit_code:duplicate.exitCode});
  await page.getByRole('button',{name:'New project',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.getByLabel('Project name',{exact:true}).fill(`Desktop smoke ${stamp}`);const projectResponse=page.waitForResponse(r=>r.url().endsWith('/api/projects')&&r.request().method()==='POST');await dialog.getByRole('button',{name:'Save project',exact:true}).click();const project=await(await projectResponse).json();
  await page.locator('.studio-sidebar nav a[aria-label="Create"]').click();await page.getByRole('tab',{name:'Text + Image',exact:true}).click();await page.getByLabel('Asset name',{exact:true}).fill('Archer Tower / real local GLB smoke');await page.locator('.prompt-input').fill('Native desktop persistence test. Preserve the real Archer Tower source; no synthetic generation or art approval.');
  const assetResponse=page.waitForResponse(r=>r.url().endsWith('/api/assets')&&r.request().method()==='POST');await page.getByRole('button',{name:'Save draft to library',exact:true}).click();const asset=await(await assetResponse).json();
  const source=path.join(root,'data/jobs/0cd41c06dfa040908ead8f880ff6593b/output/LOD2.glb');if(!fs.existsSync(source))throw Error('Actual Archer Tower GLB fixture missing');const data=fs.readFileSync(source);const importedResponse=page.waitForResponse(r=>r.url().includes('/api/import/candidate')&&r.request().method()==='POST');importedResponse.catch(()=>{});await page.getByLabel('Upload concept image').setInputFiles(source);const imported=await importedResponse;if(!imported.ok())throw Error('Actual desktop GLB file input failed');const importedSnapshot=await api(`/api/studio?project_id=${project.id}`);const artifact=importedSnapshot.assets.find(a=>a.id===asset.id)?.versions.at(-1);if(!artifact)throw Error('Uploaded native GLB version missing from Library');
  await page.reload();await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0&&Number(document.querySelector('.viewer')?.dataset.textures)>0,{timeout:90000});await page.screenshot({path:path.join(run,'desktop-model.png'),fullPage:true});
  report.checks.push({name:'real_glb_webview_and_library',passed:true,asset_id:asset.id,artifact_id:artifact.id,source_sha256:crypto.createHash('sha256').update(data).digest('hex'),triangles:artifact.metadata.triangles,actual_inference:'NOT_RUN_IN_THIS_SMOKE'});
  await page.locator('.output-contract summary').click();await page.getByRole('button',{name:'Check output route',exact:true}).click();await page.locator('.output-contract [role="status"]').waitFor();
  if((await api('/api/jobs')).length!==0)throw Error('Dry-run route unexpectedly submitted GPU work');
  const savedManifest=page.waitForResponse(r=>r.url().endsWith(`/api/platform/assets/${asset.id}/manifest`)&&r.request().method()==='POST');await page.getByRole('button',{name:'Save manifest v2',exact:true}).click();const manifestArtifact=await(await savedManifest).json();
  const manifestResponse=await fetch(first.api_base+manifestArtifact.url,{headers:{'X-AFS-Token':first.api_token}});const manifest=await manifestResponse.json();if(manifest.schema_version!=='2.0'||manifest.asset_id!==asset.id||!manifest.candidates.some(c=>c.sha256===artifact.sha256))throw Error('Native saved manifest did not preserve real model hash');
  report.checks.push({name:'native_output_routing_and_immutable_manifest_v2',passed:true,manifest_id:manifestArtifact.id,unexpected_generation_jobs:0});
  await page.locator('.studio-sidebar nav a[aria-label="Settings"]').click();await page.getByRole('heading',{name:'Windows application',exact:true}).waitFor();await page.getByRole('button',{name:'Choose library folder',exact:true}).waitFor();report.checks.push({name:'native_runtime_settings_panel',passed:true,native_dialog_interaction:'MANUAL_NOT_AUTOMATED'});
  await page.locator('.studio-sidebar nav a[aria-label="Create"]').click();await page.getByRole('tab',{name:'Batch Assets',exact:true}).click();
  await page.getByLabel('Batch Master Prompt').fill('- Castle T1-T3\n- Archer Tower T1-T3\n- Magic Tower T1-T3\n- House T1-T3\n- A modular Wall/Gate');
  const analyzed=page.waitForResponse(r=>r.url().endsWith('/api/batches/analyze')&&r.request().method()==='POST');await page.getByRole('button',{name:'Analyze Prompt',exact:true}).click();const batch=await(await analyzed).json();if(batch.items.length!==14)throw Error('Native Batch UI did not produce 14 explicit items');await page.locator('.batch-table tbody tr').nth(13).waitFor();
  if(!await page.getByRole('button',{name:'Generate Selected (14)',exact:true}).isDisabled())throw Error('Unconfirmed dimensions must block native Batch generation');
  await page.screenshot({path:path.join(run,'desktop-batch.png'),fullPage:true});report.checks.push({name:'native_batch_manifest_and_missing_specs_guard',passed:true,batch_id:batch.id,manifest_count:14});
  await close();report.checks.push({name:'graceful_close_owned_backend_exited',passed:true});await browser.close().catch(()=>{});
  child=launch();browser=await connect();page=browser.contexts()[0].pages()[0];await page.locator('.studio-sidebar').waitFor({timeout:180000});const second=await session();if(second.api_token===first.api_token)throw Error('Desktop API token was not rotated');const persisted=await api(`/api/studio?project_id=${project.id}`);const savedBatch=await api(`/api/batches/${batch.id}`);if(savedBatch.items.length!==14||!savedBatch.paused)throw Error('Native batch checkpoint lost after relaunch');if(!persisted.assets.some(a=>a.id===asset.id&&a.versions.some(v=>v.id===artifact.id)))throw Error('Library data lost after desktop relaunch');
  await page.locator('.studio-sidebar nav a[aria-label="Library"]').click();await page.getByRole('button',{name:asset.name,exact:true}).click();await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.dataset.loaded)>0&&Number(document.querySelector('.viewer')?.dataset.textures)>0,{timeout:90000});await page.screenshot({path:path.join(run,'desktop-reopened.png'),fullPage:true});await close();report.checks.push({name:'native_relaunch_persistence_and_token_rotation',passed:true});
  if(report.errors.length)throw Error('WebView JavaScript errors occurred');report.status='PASS';
}catch(error){report.status='FAILED';report.failure=String(error).replace(/([?&]afs_token=)[^&\s]+/g,'$1[redacted]');throw error;}
finally{
  fs.writeFileSync(path.join(run,'smoke-report.json'),JSON.stringify(report,null,2));fs.mkdirSync(path.join(root,'.local/desktop-build'),{recursive:true});fs.writeFileSync(path.join(root,'.local/desktop-build/latest-smoke-path.txt'),path.join(run,'smoke-report.json'));
  fs.writeFileSync(path.join(root,'docs/evidence/desktop_smoke.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,report:path.join(run,'smoke-report.json'),failure:report.failure}));if(browser)await browser.close().catch(()=>{});
}
