// Run only after the isolated acceptance backend has been stopped and restarted.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('../..'),base='http://127.0.0.1:8766';
const before=JSON.parse(await fs.readFile(path.join(root,'docs/evidence/studio_real_flow.json'),'utf8'));
assert.equal(before.status,'PASS');
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
 const page=await browser.newPage({viewport:{width:1600,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(base+'/#library');
 await page.getByRole('button',{name:'Archer Tower T3 / UI acceptance',exact:true}).waitFor();
 await page.evaluate(()=>{const el=document.createElement('div');el.textContent='REAL OUTPUT / ISOLATED QA DATABASE / WORKFLOW TEST ONLY';el.style.cssText='position:fixed;top:0;left:0;right:0;z-index:10000;background:#683d20;color:white;padding:8px;text-align:center;font-size:12px';document.body.append(el);});
 await page.screenshot({path:path.join(root,'docs/evidence/studio_library_reopened.png'),fullPage:true});
 await page.getByRole('button',{name:'Archer Tower T3 / UI acceptance',exact:true}).click();
 await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.getAttribute('data-loaded'))===1,null,{timeout:90000});
 assert((await page.getByLabel('Describe your asset').inputValue()).includes('Archer Tower T3, Runavelle.'));
 const snapshot=await (await page.request.get(base+'/api/studio')).json();
 const asset=snapshot.assets.find(a=>a.id===before.asset.id);
 assert.equal(asset.master_artifact_id,before.asset.master);assert.equal(asset.versions.length,before.asset.versions);
 assert.equal(snapshot.jobs.filter(j=>j.payload.kind==='inference').length,1);assert.equal(errors.length,0);
 before.backend_restart_verified={status:'PASS',same_asset_id:asset.id,same_master_id:asset.master_artifact_id,same_versions:asset.versions.length,errors};
 await fs.writeFile(path.join(root,'docs/evidence/studio_real_flow.json'),JSON.stringify(before,null,2));
 console.log('BACKEND_AND_BROWSER_RESTART_PASS',asset.id);
} finally {await browser.close();}
