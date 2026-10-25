// UI audit: packaged app in an isolated QA profile with seeded data; one screenshot per page, tab and modal.
// No generation is started (imports and a paused batch only). Output: .local/ui-audit/<stamp>/*.png
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import net from 'node:net';
const root=path.resolve(import.meta.dirname,'..');
const executable=process.env.AFS_SMOKE_EXE||path.join(root,'dist/windows/stable/latest/Asset Forge Studio.exe');
const stamp=new Date().toISOString().replaceAll(/[:.]/g,'-'),run=path.join(root,'.local/ui-audit',stamp),config=path.join(run,'config'),shots=path.join(run,'shots');
fs.mkdirSync(config,{recursive:true});fs.mkdirSync(shots,{recursive:true});
fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
const child=spawn(executable,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore'});
let browser;for(let n=0;n<180&&!browser;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);}catch{await sleep(1000);}}
const page=browser.contexts()[0].pages()[0];const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.locator('.studio-sidebar').waitFor({timeout:180000});
const session=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
const api=async(route,body,form)=>{const r=await fetch(session.api_base+route,{headers:{'X-AFS-Token':session.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:form?{method:'POST',body:form}:{})});const t=await r.text();if(!r.ok)throw Error(route+' '+r.status+' '+t.slice(0,200));return JSON.parse(t);};
const upload=async(route,file,fields)=>{const f=new FormData();f.append('file',new Blob([fs.readFileSync(file)]),path.basename(file));for(const[k,v]of Object.entries(fields))f.append(k,v);return api(route,null,f);};
// Seed: a game, two imported models, a paused batch from the real prompt file, one item waiting for answers.
const project=await api('/api/projects',{name:'Audit Game'});
for(const glb of ['ArcherTowerLOD2.glb','RiggedFigure.glb'])await upload('/api/library/import',path.join(root,'.local/fixtures',glb),{project_id:project.id}).catch(e=>errors.push('seed '+e.message));
const prompt=path.join(root,'prompt/Runavelle_V4_Next50.md');
let batch=null;if(fs.existsSync(prompt)){const text=fs.readFileSync(prompt,'utf8').split(/\r?\n---\r?\n/).slice(0,4).join('\n---\n');const f=new FormData();f.append('file',new Blob([text]),'audit.md');f.append('project_id',project.id);f.append('name','Audit batch');batch=await api('/api/batches/import',null,f).catch(e=>{errors.push('batch '+e.message);return null;});}
await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.locator('.studio-sidebar').waitFor();await sleep(1500);
const report=[];
async function shot(name,action,full=false){try{if(action)await action();await sleep(900);await page.screenshot({path:path.join(shots,name+'.png'),fullPage:full});report.push({name,ok:true});}catch(e){report.push({name,ok:false,error:String(e.message||e).slice(0,200)});}}
const nav=label=>page.locator('.studio-sidebar nav a',{hasText:label}).first().click();
const closeModal=async()=>{await page.keyboard.press('Escape');await sleep(300);};
await shot('01-home',()=>nav('Home'));
await shot('02-create-cards',async()=>{await nav('Create');const change=page.getByRole('button',{name:'Change workflow'});if(await change.count())await change.click();});
for(const[name,title]of[['03-create-single','Single asset'],['04-create-batch','Batch assets'],['05-create-map','Map / World'],['06-create-effects','Effects'],['07-create-motion','Motion'],['08-create-video','Video / Cinematic']]){
  await shot(name,async()=>{const change=page.getByRole('button',{name:'Change workflow'});if(await change.count())await change.click();await page.locator('.create-workflow-card',{hasText:title}).first().click();},name==='06-create-effects');}
await shot('09-production',async()=>{await nav('Production');const row=page.locator('.production-row button, .production-explorer button').filter({hasText:/./}).nth(1);if(await row.count())await row.click();});
for(const tab of['Overview','Sources','Checks','Refine','Log'])await shot('10-inspector-'+tab.toLowerCase(),()=>page.getByRole('tab',{name:tab}).click());
await shot('11-library',()=>nav('Library'));
await shot('12-library-detail',()=>page.locator('.library-managed-card').first().click());
await shot('13-delete-modal',()=>page.getByRole('button',{name:/^Delete/}).first().click());await closeModal();
await shot('14-export-modal',async()=>{await nav('Production');const b=page.getByRole('button',{name:/Export model/}).first();if(await b.count())await b.click();});await closeModal();
await shot('15-notifications',()=>page.locator('button[aria-label*="otification"]').first().click());await closeModal();
await shot('16-settings',()=>nav('Settings'));
fs.writeFileSync(path.join(run,'report.json'),JSON.stringify({executable,project:project.id,batch:batch?.id,shots:report,errors},null,2));
await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});for(let n=0;n<60&&child.exitCode===null;n++)await sleep(250);
await browser.close().catch(()=>{});
console.log(JSON.stringify({run,shots:report.map(r=>r.name+(r.ok?'':' FAIL '+r.error)),errors},null,1));
