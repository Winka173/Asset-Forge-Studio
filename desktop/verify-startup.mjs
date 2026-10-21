// Actual native startup with an absent external AI workspace; no GPU inference/download.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const run=path.join(root,'.local/desktop-startup',new Date().toISOString().replaceAll(/[:.]/g,'-'));fs.mkdirSync(run,{recursive:true});
const absent=path.join(run,'not-installed-ai-workspace');const library=path.join(run,'Library');
fs.writeFileSync(path.join(run,'desktop-config.json'),JSON.stringify({workspace:absent,library,blender:null,setup_complete:false}));
const child=spawn(path.join(root,'dist/windows/latest/Asset Forge Studio.exe'),[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:run,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port=19389'},stdio:'ignore',windowsHide:false});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));let browser,page;const report={status:'RUNNING',run,scope:'Actual packaged backend and setup without existing AI workspace; not a clean-machine or inference test'};
try{
 for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP('http://127.0.0.1:19389');break;}catch{await sleep(1000);}}
 assert(browser);page=browser.contexts()[0].pages()[0];await page.getByRole('button',{name:'Open studio',exact:true}).waitFor({timeout:180000});
 const session=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));assert.equal(session.phase,'READY');assert.equal(session.workspace,absent);assert(!fs.existsSync(absent));
 await page.screenshot({path:path.join(run,'missing-workspace-setup.png')});await page.getByRole('button',{name:'Open studio',exact:true}).click();await page.locator('.studio-sidebar').waitFor();
 report.version=session.version;report.backend_pid=session.backend_pid;report.checks=['Bundled backend ready without external AI workspace','First-run setup rendered','Studio opened without dev Python or model loading'];
 await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<180&&child.exitCode===null;n++)await sleep(500);assert.notEqual(child.exitCode,null);report.status='PASS_NATIVE_MISSING_WORKSPACE_STARTUP';
}catch(e){report.status='FAILED';report.failure=String(e);process.exitCode=1;}
finally{fs.writeFileSync(path.join(root,'docs/evidence/desktop_startup.json'),JSON.stringify(report,null,2));if(browser)await browser.close().catch(()=>{});console.log(JSON.stringify(report));}
