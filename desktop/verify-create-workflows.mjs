// Packaged app, isolated Library, real engines: every Create workflow opens with the shared step bar, and the light-weight
// generators (flipbook effect, mesh effect, map layout, 2D sprite batch) really run to a validated result.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'),stamp=new Date().toISOString().replaceAll(/[:.]/g,'-'),run=path.join(root,'.local/create-workflows',stamp),config=path.join(run,'config');
fs.mkdirSync(config,{recursive:true});fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^﻿/,'')),exe=process.env.AFS_SMOKE_EXE||path.join(build.delivery_location,build.executable);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));const l=net.createServer();await new Promise(r=>l.listen(0,'127.0.0.1',r));const port=l.address().port;await new Promise(r=>l.close(r));
const report={executable:exe,checks:[],errors:[]};
const check=(name,ok,detail='')=>{report.checks.push({name,ok:!!ok,detail:String(detail).slice(0,300)});console.log((ok?'PASS ':'FAIL ')+name+(detail?' | '+String(detail).slice(0,160):''));};
const child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore'});
let browser;for(let n=0;n<180&&!browser;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);}catch{await sleep(1000);}}
const page=browser.contexts()[0].pages()[0];page.on('pageerror',e=>report.errors.push(e.message));
await page.locator('.studio-sidebar').waitFor({timeout:180000});
const s=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
const api=async(route,body)=>{const r=await fetch(s.api_base+route,{headers:{'X-AFS-Token':s.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});const t=await r.text();if(!r.ok)throw Error(`${route} ${r.status} ${t.slice(0,200)}`);return JSON.parse(t);};
const TERMINAL=['REVIEW_REQUIRED','COMPLETED','EXPORTED','FAILED','BLOCKED','CANCELLED'];
const kindOf=j=>j.kind||j.payload.kind||'';
async function settle(projectId,minutes=25,need=[]){const t0=Date.now();let last=[];await sleep(4000);while(Date.now()-t0<minutes*60000){const jobs=(await api('/api/jobs')).filter(j=>j.payload.project_id===projectId);last=jobs;const have=need.every(k=>jobs.some(j=>kindOf(j)===k));if(have&&jobs.length&&jobs.every(j=>TERMINAL.includes(j.status)))break;await sleep(5000);}return last;}
const project=await api('/api/projects',{name:'Create workflows acceptance'});
await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.locator('.studio-sidebar').waitFor();await sleep(2000);
// 1. every workflow opens with the shared step bar and returns to the hub
for(const [title,first] of [['Single asset','Describe asset'],['Batch assets','Brief'],['Map / World','Describe'],['Effects','Describe'],['Motion','Describe'],['Video / Cinematic','Scene']]){
  try{
    await page.locator('.studio-sidebar nav a',{hasText:'Create'}).first().click();await sleep(600);
    for(const label of ['Change workflow','Choose workflow']){const b=page.getByRole('button',{name:label});if(await b.count()){await b.first().click();break;}}
    await page.locator('.create-workflow-card',{hasText:title}).first().click();await sleep(1200);
    const bar=page.locator('.create-stepper').first();await bar.waitFor({timeout:8000});const text=await bar.innerText();
    check(`${title}: step bar shows Choose workflow + ${first}`,/Choose workflow/.test(text)&&text.includes(first),text.replace(/\n/g,' | '));
    await bar.getByRole('button',{name:/Choose workflow/}).click();await page.locator('.create-workflow-card').first().waitFor({timeout:8000});
    check(`${title}: Choose workflow returns to the hub`,true);
  }catch(e){check(`${title}: opens`,false,e.message);}
}
// 2. flipbook effect (Blender, CPU)
try{
  await api('/api/fx/flipbook',{project_id:project.id,prompt:'small campfire',preset:'campfire',quality:'Fast',frames:16,cell:128,request_id:'wf-flip-'+Date.now().toString(36)});
  const jobs=await settle(project.id,20,['fx_flipbook']);const fx=jobs.filter(j=>/flipbook/.test(kindOf(j)));
  check('Effects: flipbook reaches a validated result',fx.length&&fx.every(j=>j.status==='REVIEW_REQUIRED'),fx.map(j=>j.status+' '+(j.error||'')).join('; '));
}catch(e){check('Effects: flipbook',false,e.message);}
// 3. mesh effect
try{
  await api('/api/fx/mesh',{project_id:project.id,kind:'shockwave',request_id:'wf-mesh-'+Date.now().toString(36)});
  const jobs=await settle(project.id,10,['fx_mesh']);const mesh=jobs.filter(j=>/mesh/.test(kindOf(j)));
  check('Effects: mesh effect (GLB) reaches a validated result',mesh.length&&mesh.every(j=>j.status==='REVIEW_REQUIRED'),mesh.map(j=>j.status+' '+(j.error||'')).join('; '));
}catch(e){check('Effects: mesh effect',false,e.message);}
// 4. map layout (preview, save; the Unity build is not part of this check)
try{
  const plan=await api('/api/world/preview-plan',{project_id:project.id,name:'Acceptance map',prompt:'Two-lane tower-defense map with a river',seed:7});
  check('Map: layout preview is produced',plan&&Object.keys(plan).length>0,Object.keys(plan).join(','));
  const saved=await api('/api/world/plans',{plan:plan.plan||plan,request_id:'wf-plan-'+Date.now().toString(36)});
  check('Map: layout saved as an asset',saved&&(saved.asset_id||saved.id||saved.asset),Object.keys(saved).join(','));
}catch(e){check('Map: layout',false,e.message);}
// 5. 2D sprite batch (concept engine on the GPU)
try{
  const b=await api('/api/batches/analyze',{project_id:project.id,name:'Sprites',master_prompt:'- cartoon pet cat with wings, standing',mode:'Maximum Quality Batch',output:'2d'});
  check('Batch: 2D manifest analysed',b.items?.length===1,`${b.items?.length} item(s)`);
  await api(`/api/batches/${b.id}/run-all`,{request_id:'wf-sprite-'+Date.now().toString(36)});
  const jobs=await settle(project.id,25,['concept','sprite_cutout']);const sp=jobs.filter(j=>['concept','sprite_cutout'].includes(kindOf(j)));
  check('Batch: 2D sprites finish (concepts then cut-outs)',sp.length>=2&&sp.every(j=>j.status==='REVIEW_REQUIRED'),sp.map(j=>kindOf(j)+':'+j.status).join(', '));
}catch(e){check('Batch: 2D sprites',false,e.message);}
check('No page errors in the UI',report.errors.length===0,report.errors.join(' | '));
report.status=report.checks.every(c=>c.ok)?'PASS':'FAIL';fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));
await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});for(let n=0;n<60&&child.exitCode===null;n++)await sleep(500);await browser.close().catch(()=>{});
console.log(JSON.stringify({status:report.status,run}));process.exit(report.status==='PASS'?0:1);
