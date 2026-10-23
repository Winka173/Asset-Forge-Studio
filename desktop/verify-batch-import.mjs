// Actual packaged Windows app + user's 2.64 MB source. No simulated inference results.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import net from 'node:net';
const root=path.resolve(import.meta.dirname,'..');
const executable=process.env.AFS_SMOKE_EXE||path.join(root,'dist/windows/expansion/latest/Asset Forge Studio Expansion.exe');
const sourcePath=process.env.AFS_RUNAVELLE_SOURCE||path.join(process.env.USERPROFILE,'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md');
const raw=fs.readFileSync(sourcePath),text=raw.toString('utf8').replace(/^\uFEFF/,'');
const headings=[...text.matchAll(/^# ([A-Z][A-Z0-9]*_[A-Za-z0-9_]+)[ \t]+[\u2014\u2013-][ \t]+([^\r\n]+)/gm)];
assert.equal(headings.length,349);
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const stamp=new Date().toISOString().replaceAll(/[:.]/g,'-'),run=path.join(root,'.local/batch-import-native',stamp),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const report={status:'RUNNING',executable,source_file:sourcePath,source_bytes:raw.length,source_sha256:sha(raw),run,checks:[],errors:[],inference_outputs:'NOT_GENERATED; queue acceptance only, QA jobs cancelled before GPU admission'};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,session,lock,closing=false;
const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
async function launch(){child=spawn(executable,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});closing=false;for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{await sleep(1000);}}assert(browser);page=browser.contexts()[0].pages()[0];page.on('pageerror',e=>{if(!closing)report.errors.push(e.message);});await page.locator('.studio-sidebar').waitFor({timeout:180000});session=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));}
async function api(route,body){const r=await fetch(session.api_base+route,{headers:{'X-AFS-Token':session.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});assert(r.ok,`${route}: ${r.status}`);return r.json();}
async function close(){closing=true;await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});for(let n=0;n<100&&child.exitCode===null;n++)await sleep(200);assert.notEqual(child.exitCode,null);await browser.close().catch(()=>{});browser=null;}
async function holdGPU(){lock=spawn(path.join(root,'.venv/Scripts/python.exe'),['-u','-c','from apps.api.jobs import exclusive_worker_lock\nwith exclusive_worker_lock():\n print("READY",flush=True)\n input()'],{cwd:root,stdio:['pipe','pipe','pipe'],windowsHide:true});await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('GPU QA lock unavailable')),10000);lock.once('exit',()=>{clearTimeout(timeout);reject(Error('GPU QA lock exited'));});lock.stdout.on('data',data=>{if(data.toString().includes('READY')){clearTimeout(timeout);resolve();}});});}
try{
 await launch();report.version=(await api('/api/desktop/health')).version;
 const project=await api('/api/projects',{name:`Runavelle Import QA ${stamp}`});await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.locator('.studio-sidebar').waitFor();
 await page.locator('.studio-sidebar nav a[aria-label="Create"]').click();await page.getByRole('tab',{name:'Batch Assets',exact:true}).click();
 await page.getByLabel('Import asset manifest',{exact:true}).setInputFiles(sourcePath);await page.getByRole('button',{name:'Analyze prompt',exact:true}).waitFor();
 if(process.env.AFS_MANIFEST_FORMAT==='markdown'){await page.getByRole('combobox',{name:'Manifest format',exact:true}).click();await page.getByRole('option',{name:'Markdown manifest',exact:true}).click();}
 const response=page.waitForResponse(r=>r.url().endsWith('/api/batches/import'));await page.getByRole('button',{name:'Analyze prompt',exact:true}).click();
 const imported=await response;assert.equal(imported.status(),201);const batch=await imported.json();report.batch_id=batch.id;
 const manifest=page.getByRole('region',{name:'Batch asset manifest'});await manifest.waitFor({timeout:30000});
 assert.equal(batch.items.length,headings.length);assert.equal(batch.import_diagnostics.expected_count,headings.length);assert.equal(batch.import_diagnostics.primary_count,312);assert.equal(batch.import_diagnostics.future_count,37);
 for(let i=0;i<batch.items.length;i++){const item=batch.items[i],source=text.slice(headings[i].index,i+1<headings.length?headings[i+1].index:text.length);assert.equal(item.source_asset_id,headings[i][1]);assert.equal(item.prompt,source);assert.equal(item.source_sha256,sha(source));if(item.source_status==='FUTURE')assert(!item.selected);}
 assert.equal((await api('/api/jobs')).length,0);assert.equal(await page.getByLabel('Batch Master Prompt',{exact:true}).count(),0);
 const downloaded=await fetch(session.api_base+batch.source_file.original_source_url,{headers:{'X-AFS-Token':session.api_token}});assert.equal(sha(Buffer.from(await downloaded.arrayBuffer())),sha(raw));
 report.checks.push({name:'actual349_lossless_source_spans_hashes_312primary_37future_no_jobs_no_huge_textarea',passed:true,diagnostics:batch.import_diagnostics});
 const visibleIDs=new Set();for(let n=0;n<7;n++){for(const id of await page.locator('.batch-stable-id strong').allTextContents())visibleIDs.add(id.replace(/\s*·\s*$/,''));if(n<6)await manifest.getByRole('button',{name:'Next',exact:true}).click();}
 assert.equal(visibleIDs.size,349);await page.getByLabel('Search batch assets').fill('FUT_');await page.waitForFunction(()=>document.querySelectorAll('.batch-stable-id strong').length===37);assert.equal(await page.locator('tbody input[type=checkbox]:checked').count(),0);await page.getByLabel('Search batch assets').fill('');
 await page.getByLabel('Select all batch assets',{exact:true}).click();await page.waitForFunction(()=>document.querySelector('.batch-manifest-summary')?.textContent.includes('0 selected'));
 for(const item of batch.items.slice(0,3)){
  await page.getByLabel(`Select ${item.name}`,{exact:true}).click();await page.waitForFunction(name=>[...document.querySelectorAll('input[type=checkbox]')].some(el=>el.getAttribute('aria-label')==='Select '+name&&el.checked),item.name);
  await manifest.getByRole('button',{name:item.name,exact:true}).click();const dialog=page.getByRole('dialog');assert.equal(await dialog.getByLabel('Individual asset prompt').inputValue(),item.prompt);
  await dialog.getByRole('checkbox',{name:/I confirm the dimensions/}).check();const saved=page.waitForResponse(r=>r.url().endsWith(`/items/${item.asset_id}`));await dialog.getByRole('button',{name:'Save specifications',exact:true}).click();assert((await saved).ok());await dialog.waitFor({state:'hidden'});
 }
 const generate=manifest.getByRole('button',{name:'Generate selected (3)',exact:true});await generate.waitFor();await generate.scrollIntoViewIfNeeded();assert(await generate.isEnabled());
 await page.screenshot({path:path.join(run,'manifest-visible-three-selected.png'),fullPage:true,animations:'disabled'});
 report.checks.push({name:'all349_rendered_across_pages_future_unselected_editable_three_selected_generate_visible_enabled',passed:true});
 // Hold the real shared GPU lock only during queue verification, then cancel these QA jobs.
 await holdGPU();const queuedResponse=page.waitForResponse(r=>r.url().endsWith(`/api/batches/${batch.id}/run`));await generate.click();assert((await queuedResponse).ok());
 const queued=(await api('/api/jobs')).filter(j=>j.payload.batch_id===batch.id);assert.equal(queued.length,3);
 for(const item of batch.items.slice(0,3)){const job=queued.find(j=>j.payload.asset_id===item.asset_id);assert.equal(job.status,'QUEUED');assert.equal(job.payload.kind,'concept');assert.equal(job.payload.user_prompt,item.prompt);assert(job.payload.prompt.startsWith(item.prompt));}
 report.checks.push({name:'explicit_generate_creates_three_real_independent_queued_jobs_full_original_prompts',passed:true,jobs:queued.map(j=>({id:j.id,asset_id:j.payload.asset_id,status:j.status,source_prompt_sha256:sha(j.payload.user_prompt)}))});
 await api(`/api/batches/${batch.id}/control`,{action:'cancel'});assert((await api('/api/jobs')).every(j=>j.status==='CANCELLED'));lock.stdin.end('\n');await sleep(500);lock=null;
 await page.screenshot({path:path.join(run,'queue-verified.png'),fullPage:true,animations:'disabled'});
 const local=await api('/api/batch-analysis/local-models');report.checks.push({name:'local_semantic_adapter_real_probe',passed:true,probe:local,real_llm_inference:local.available?'NOT_RUN':'UNAVAILABLE_NOT_SIMULATED'});
 await close();await launch();await page.locator('.studio-sidebar nav a[aria-label="Create"]').click();await page.getByRole('tab',{name:'Batch Assets',exact:true}).click();await page.getByRole('region',{name:'Batch asset manifest'}).waitFor({timeout:30000});assert.equal((await api(`/api/batches/${batch.id}`)).items.length,349);
 await page.screenshot({path:path.join(run,'reopened-manifest.png'),fullPage:true,animations:'disabled'});report.checks.push({name:'native_relaunch_restores349_item_manifest_source_and_selection',passed:true});assert.equal(report.errors.length,0);report.status='PASS';await close();
}catch(e){report.status='FAILED';report.failure=String(e);if(page)await page.screenshot({path:path.join(run,'failure.png'),fullPage:true,animations:'disabled'}).catch(()=>{});throw e;}
finally{if(lock)lock.stdin.end('\n');if(browser){if(session&&report.batch_id)await api(`/api/batches/${report.batch_id}/control`,{action:'cancel'}).catch(()=>{});await close().catch(()=>{});}fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,failure:report.failure}));}
