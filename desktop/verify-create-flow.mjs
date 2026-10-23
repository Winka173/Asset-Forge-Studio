// Run against isolated AFS_DATA API on 8765 and Vite on 5173. Never points at the production Library.
import { chromium } from '../apps/web/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fillAssetName,readAssetName,toGenerateStep} from './ui-helpers.mjs';
const base='http://127.0.0.1:8765';
async function api(url,body){const response=await fetch(base+url,{...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});assert(response.ok,await response.clone().text());return response.json();}
const project=await api('/api/projects',{name:'Isolated Create Wizard UI QA'});
await api('/api/production/control',{scope:'all',action:'pause'});
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1536,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
await page.goto('http://127.0.0.1:5173');await page.evaluate(id=>localStorage.setItem('afs.project',id),project.id);await page.reload();await page.locator('.studio-sidebar').waitFor();await page.getByRole('link',{name:'Create',exact:true}).click();await page.getByRole('heading',{name:'What would you like to create?'}).waitFor();
assert.equal(await page.locator('.create-workflow-card').count(),4);assert.equal(await page.locator('.prompt-input').count(),0);
await page.screenshot({path:'.local/create-wizard-ui/01-workflows.png',fullPage:true,animations:"disabled"});
await page.getByRole('button',{name:'Single asset One prompt'}).click();await page.locator('.prompt-input').fill('Stone archer tower, blue roof, height 9 m.');await fillAssetName(page,'Wizard Archer QA');assert.equal(await page.getByRole('button',{name:'Generate & export asset',exact:true}).count(),0);
await page.screenshot({path:'.local/create-wizard-ui/02-describe.png',fullPage:true,animations:"disabled"});await toGenerateStep(page);await page.getByRole('button',{name:'Generate & export asset',exact:true}).waitFor();assert.equal(await page.locator('.prompt-input').count(),0);assert.equal(await page.getByRole('combobox',{name:'Single workflow mode'}).isVisible(),false);await page.screenshot({path:'.local/create-wizard-ui/03-generate.png',fullPage:true,animations:"disabled"});
await page.reload();await page.getByRole('button',{name:'Generate & export asset',exact:true}).waitFor();await page.getByRole('button',{name:'Edit input',exact:true}).click();assert.equal(await page.locator('.prompt-input').inputValue(),'Stone archer tower, blue roof, height 9 m.');await toGenerateStep(page);
const response=page.waitForResponse(r=>r.url().endsWith('/api/automation/single'));await page.getByRole('button',{name:'Generate & export asset',exact:true}).click();const result=await(await response).json();assert(result.batch_id);await page.getByRole('region',{name:'Production Workspace',exact:true}).waitFor();assert.equal((await api('/api/jobs')).filter(j=>j.status==='RUNNING').length,0);await api(`/api/batches/${result.batch_id}/control`,{action:'cancel'});
await page.getByRole('link',{name:'Create',exact:true}).click();await page.getByRole('heading',{name:'What would you like to create?'}).waitFor();await page.getByRole('button',{name:'Single asset One prompt'}).click();assert.equal(await page.locator('.prompt-input').inputValue(),'');assert.equal(await readAssetName(page),'');
await page.getByRole('button',{name:'Change workflow',exact:true}).click();await page.getByRole('button',{name:'Effects Create sword'}).click();await page.getByLabel('Effect prompt').fill('Fire sword slash');await page.keyboard.press('Control+Enter');await page.waitForTimeout(500);assert.equal((await api('/api/jobs')).filter(j=>j.status==='RUNNING').length,0);assert.equal((await api('/api/studio?project_id='+project.id)).assets.length,1);await page.screenshot({path:'.local/create-wizard-ui/04-effects.png',fullPage:true,animations:"disabled"});
assert.deepEqual(errors,[]);console.log(JSON.stringify({status:'PASS',project:project.id,checks:['real backend persisted draft','3 steps','4 real workflows','refresh restores step and prompt','explicit Generate only into globally paused queue','fresh Create clears prior asset','Ctrl+Enter in FX never submits Single'],errors}));
}finally{await browser.close();}



