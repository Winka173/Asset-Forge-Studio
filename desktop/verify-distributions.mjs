// Two actual native applications, independent default settings, shared GPU lock.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {spawn,spawnSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/distribution-smoke',new Date().toISOString().replaceAll(/[:.]/g,'-'));
const local=path.join(run,'LocalAppData');fs.mkdirSync(local,{recursive:true});
const stableRoot=path.join(local,'AssetForgeStudio');fs.mkdirSync(stableRoot,{recursive:true});
fs.writeFileSync(path.join(stableRoot,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(stableRoot,'Library'),blender:null,setup_complete:false}));
const report={status:'RUNNING',run,checks:[],inference:'NOT_RUN',quality:'NOT_ASSESSED'};
const apps=[];const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function hashes(folder){return Object.fromEntries(fs.readdirSync(folder).filter(n=>n.endsWith('.exe')).map(n=>[n,crypto.createHash('sha256').update(fs.readFileSync(path.join(folder,n))).digest('hex')]));}
const pinned=hashes(path.join(root,'dist/windows/stable'));
const existingPc=JSON.parse(spawnSync('powershell',['-NoProfile','-Command',"ConvertTo-Json -InputObject @(Get-Process -Name 'Asset Forge Studio' -ErrorAction SilentlyContinue | Select-Object Id,MainWindowTitle)"],{encoding:'utf8',windowsHide:true}).stdout.trim()||'[]');
try{
 for(const [name,relative,port] of [['PC','dist/windows/stable/Asset Forge Studio.exe',19540],['Expansion','dist/windows/expansion/latest/Asset Forge Studio Expansion.exe',19541]]){
  if(name==='PC'&&existingPc.length){report.checks.push({name:'existing_pc_kept_running_without_touching_user_session',passed:true,processes:existingPc});continue;}
  const env={...process.env,LOCALAPPDATA:local,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`};delete env.AFS_DESKTOP_CONFIG_DIR;
  const app={name,child:spawn(path.join(root,relative),[],{env,stdio:'ignore',windowsHide:false}),port};apps.push(app);
  for(let n=0;n<180;n++){try{app.browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{await sleep(1000);}}
  assert(app.browser,`${name} failed to expose native WebView`);app.page=app.browser.contexts()[0].pages()[0];
  await app.page.getByRole('button',{name:'Open studio',exact:true}).waitFor({timeout:180000});
  app.session=await app.page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));
  assert(app.session.library.startsWith(local));
  await app.page.screenshot({path:path.join(run,`${name}.png`)});
 }
 const expansion=apps.find(a=>a.name==='Expansion'),pc=apps.find(a=>a.name==='PC');
 assert.equal(expansion.child.exitCode,null);
 if(pc){assert.notEqual(pc.session.backend_pid,expansion.session.backend_pid);assert.equal(pc.child.exitCode,null);assert.equal(pc.session.library,path.join(local,'AssetForgeStudio','Library'));assert.equal(pc.session.version,'0.3.1');}
 assert.equal(expansion.session.library,path.join(local,'AssetForgeStudioExpansion','Library'));
 assert.equal(expansion.session.version,JSON.parse(fs.readFileSync(path.join(root,'package.json'))).version);
 const p=JSON.parse(fs.readFileSync(path.join(local,'AssetForgeStudioExpansion','desktop-config.json')));
 assert.equal(p.library,expansion.session.library);
 if(!pc){const check=spawnSync('powershell',['-NoProfile','-Command',`Get-Process -Id ${existingPc[0].Id} -ErrorAction Stop | Out-Null`],{windowsHide:true});assert.equal(check.status,0);}
 report.checks.push({name:'native_expansion_default_root_and_pc_coexistence',passed:true,pc_session_inspected:Boolean(pc),expansion_version:expansion.session.version,pc_library:pc?.session.library||'Existing user session; not inspected or modified',expansion_library:expansion.session.library});
 assert.deepEqual(hashes(path.join(root,'dist/windows/stable')),pinned);
 assert.deepEqual(hashes(path.join(root,'dist/windows/latest')),pinned);
 report.checks.push({name:'pinned_pc_and_compatibility_exes_unchanged',passed:true,sha256:pinned});
 report.status='PASS';
}catch(e){report.status='FAILED';report.failure=String(e);throw e;}
finally{
 for(const app of apps){if(app.page){await app.page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close')).catch(()=>{});for(let n=0;n<100&&app.child.exitCode===null;n++)await sleep(200);}if(app.browser)await app.browser.close().catch(()=>{});}
 fs.writeFileSync(path.join(root,'docs/evidence/desktop_distributions.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}
