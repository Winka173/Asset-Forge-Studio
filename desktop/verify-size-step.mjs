// Packaged WebView2: Single Create -> Size & scale step (real reference models, independent axes, sliders) -> Options step. No GPU work.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import fs from 'node:fs';import path from 'node:path';import net from 'node:net';import assert from 'node:assert/strict';import {spawn} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'),stamp=new Date().toISOString().replaceAll(/[:.]/g,'-'),run=path.join(root,'.local/size-step-native',stamp),config=path.join(run,'config');fs.mkdirSync(config,{recursive:true});fs.writeFileSync(path.join(config,'desktop-config.json'),JSON.stringify({workspace:root,library:path.join(run,'Library'),blender:null,setup_complete:true}));
const build=JSON.parse(fs.readFileSync(path.join(root,'docs/evidence/desktop_build.json'),'utf8').replace(/^﻿/,'')),exe=process.env.AFS_SMOKE_EXE||path.join(build.delivery_location,build.executable),server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));const sleep=ms=>new Promise(r=>setTimeout(r,ms));let child,browser,page,runtime,closing=false;
const report={status:'RUNNING',run,executable:exe,checks:[],errors:[],failed_requests:[],scope:'Actual Windows Size & scale step UI; no generation'};
const check=(name,passed,detail)=>{report.checks.push({name,passed,detail,errors_so_far:report.errors.length});assert(passed,`${name}: ${JSON.stringify(detail)}`);};
async function api(url,body){const r=await fetch(runtime.api_base+url,{headers:{'X-AFS-Token':runtime.api_token,...(body?{'Content-Type':'application/json'}:{})},...(body?{method:'POST',body:JSON.stringify(body)}:{})});assert(r.ok,`${url}: ${r.status}`);return r.json();}
async function launch(){closing=false;child=spawn(exe,[],{env:{...process.env,AFS_DESKTOP_CONFIG_DIR:config,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`},stdio:'ignore',windowsHide:false});for(let n=0;n<180;n++){try{browser=await chromium.connectOverCDP(`http://127.0.0.1:${port}`);break;}catch{await sleep(1000);}}page=browser.contexts()[0].pages()[0];page.on('pageerror',e=>{if(!closing)report.errors.push(e.message+' @ '+(report.checks.at(-1)?.name||'start')+' '+page.url());});page.on('requestfailed',r=>report.failed_requests.push(r.url()));page.on('response',r=>{if(r.url().includes('size-references')&&!r.ok())report.failed_requests.push(r.url()+' '+r.status());});await page.locator('.studio-sidebar').waitFor({timeout:180000});runtime=await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_bootstrap'));}
async function close(){closing=true;await page.evaluate(()=>window.__TAURI__.core.invoke('desktop_request_close'));for(let n=0;n<100&&child.exitCode===null;n++)await sleep(200);await browser.close().catch(()=>{});browser=null;}
const value=label=>page.getByLabel(label,{exact:true}).inputValue().then(Number);
try{
 await launch();await page.setViewportSize({width:1536,height:960});
 await page.getByRole('button',{name:'New project',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.getByLabel('Project name',{exact:true}).fill('Size step QA');
 const saved=page.waitForResponse(r=>r.url().endsWith('/api/projects')&&r.request().method()==='POST');await dialog.getByRole('button',{name:'Save project',exact:true}).click();const project=await(await saved).json();
 await api('/api/production/control',{scope:'all',action:'pause'});await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.locator('.studio-sidebar').waitFor();
 await page.getByRole('link',{name:'Create',exact:true}).click();await page.getByRole('button',{name:/Single asset/}).click();
 await page.getByRole('textbox',{name:/Describe your asset/}).fill('A medieval stone watchtower with a wooden roof');
 await page.getByRole('button',{name:'Continue',exact:true}).click();
 await page.locator('.size-preview-scene canvas').waitFor();await page.getByRole('button',{name:'Continue to options'}).waitFor();
 check('four_single_steps',(await page.locator('.create-stepper li').count())===4,await page.locator('.create-stepper').innerText());
 await sleep(6000);await page.screenshot({path:path.join(run,'size-step.png')});
 const refs=await page.locator('.size-preview-refs button').evaluateAll(b=>b.map(x=>({label:x.textContent,disabled:x.disabled})));
 check('real_reference_models_load',report.failed_requests.filter(u=>u.includes('size-references')&&!u.includes('dwarf')).length===0&&refs.length>=6,{refs,failed:report.failed_requests});
 const ai=page.getByRole('switch',{name:/Let AI decide the size/});check('ai_decides_by_default',await ai.isChecked(),null);
 const before={w:await value('Width (m)'),d:await value('Depth (m)'),h:await value('Height (m)')};
 await page.getByLabel('Width (m)',{exact:true}).fill(String(before.w+3));await sleep(300);
 const after={w:await value('Width (m)'),d:await value('Depth (m)'),h:await value('Height (m)')};
 check('axes_independent_by_default',after.w===before.w+3&&after.h===before.h&&after.d===before.d,{before,after});
 check('manual_edit_switches_ai_off',!(await ai.isChecked()),null);
 const slider=page.getByLabel('Height slider',{exact:true});await slider.focus();for(let n=0;n<60;n++)await page.keyboard.press('ArrowRight');await sleep(300);
 const slid=await value('Height (m)');check('height_slider_in_canvas_resizes',slid>after.h&&await value('Width (m)')===after.w,{from:after.h,to:slid});
 await page.locator('.size-preview-scene canvas').evaluate(c=>{c.dataset.qa='same';});
 for(const id of ['Small · house 6 m','Large · castle 24 m','Dwarf 1.3 m','Dragon boss 7 m'])await page.getByRole('button',{name:id,exact:true}).click();await sleep(5000);
 check('adding_references_keeps_canvas',await page.locator('.size-preview-scene canvas[data-qa="same"]').count()===1,null);
 await page.screenshot({path:path.join(run,'size-step-references.png')});
 await ai.check();await sleep(500);check('ai_switch_restores_suggestion',await ai.isChecked()&&await value('Height (m)')===before.h,{h:await value('Height (m)'),suggested:before.h});
 await page.getByRole('button',{name:'Continue to options'}).click();
 await page.getByRole('switch',{name:'Allow questions'}).waitFor();check('allow_questions_switch_on_options_step',true,null);
 await page.locator('.create-settings-step details').evaluateAll(all=>all.forEach(d=>{d.open=true;}));await sleep(500);
 const engines=await page.locator('.engine-option').evaluateAll(all=>all.map(e=>({text:e.textContent,checked:e.querySelector('input').checked,disabled:e.querySelector('input').disabled})));
 check('four_engines_with_requirements',engines.length===4&&engines.every(e=>/GPU/.test(e.text)&&!e.disabled),engines);check('trellis2_is_default',engines[0]?.checked===true&&engines.filter(e=>e.checked).length===1,engines.map(e=>e.checked));
 await page.screenshot({path:path.join(run,'options-step.png')});
 check('no_page_errors',report.errors.length===0,report.errors);
 report.status='PASS';
}catch(e){report.status='FAILED';report.error=String(e);if(page)await page.screenshot({path:path.join(run,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
finally{if(browser)await close().catch(()=>{});fs.writeFileSync(path.join(run,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,run,error:report.error}));}
