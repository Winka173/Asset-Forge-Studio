// Real local inference acceptance, isolated DB on 8766. No mocked API/model output.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = path.resolve('../..');
const base = process.env.AFS_ACCEPTANCE_URL || 'http://127.0.0.1:8766';
if (!base.endsWith(':8766')) throw new Error('Mutating acceptance requires separate 8766 test server');
const evidence = {purpose:'Real UI/pipeline acceptance only; not artist approval or production Meshy comparison', base, events:[], errors:[]};
const browser = await chromium.launch({channel:'chrome',headless:true});
let context = await browser.newContext({viewport:{width:1600,height:1100}});
let page = await context.newPage();
page.on('pageerror', e => evidence.errors.push(String(e)));
async function snapshot() { const r = await page.request.get(base+'/api/studio'); assert(r.ok()); return r.json(); }
async function waitFor(condition, label, timeout=600000) {
  const until = Date.now()+timeout;
  while (Date.now()<until) { const data=await snapshot(); if (await condition(data)) return data; await new Promise(r=>setTimeout(r,2000)); }
  throw new Error('Timeout '+label);
}
try {
  await page.goto(base+'/#create');
  const existing = await snapshot();
  const existingJob = existing.jobs.find(j=>j.payload.kind==='inference');
  let generation;
  const prompt='Archer Tower T3, Runavelle. Slate blue roof, limestone tower, timber balconies, cyan crystal. Preserve concept silhouette; inspect roof, geometry and unseen back. QA workflow only, no Meshy parity approval.';
  if (existingJob) {
    generation={jobs:[existingJob],engine:existingJob.payload.engine};
    evidence.events.push('Resumed observation of existing real acceptance job; no generation resubmitted');
  } else {
  await page.getByLabel('Asset name',{exact:true}).fill('Archer Tower T3 / UI acceptance');
  await page.getByRole('tab',{name:'Text + Image',exact:true}).click();
  await page.getByLabel('Describe your asset').fill(prompt);
  await page.getByLabel('Upload concept image').setInputFiles(path.join(root,'data/generation/trellis2/20261021T140717_42_c0d7b7/output/source_alpha.png'));
  await page.getByLabel('Engine',{exact:true}).selectOption('auto');
  await page.locator('.quality-options button').filter({hasText:/^Fast$/}).click();
  // This intentionally tests the fast real path; it is not the maximum-quality tournament.
  await page.waitForTimeout(1200);
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/studio/generate')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Generate 3D',exact:true}).click();
  const response=await responsePromise; assert(response.ok(),await response.text());
  generation=await response.json();
  }
  evidence.generation=generation;
  const jobId=generation.jobs[0].id; const assetId=generation.jobs[0].payload.asset_id;
  assert.equal(generation.jobs.length,1);
  await page.reload();
  let state=await snapshot(); assert.equal(state.jobs.filter(j=>j.payload.kind==='inference').length,1);
  assert.equal(state.draft.prompt,prompt);
  console.log('OBSERVE_REAL_INFERENCE',jobId,assetId);
  state=await waitFor(d=>d.jobs.find(j=>j.id===jobId)?.status==='REVIEW_REQUIRED'||['FAILED','BLOCKED'].includes(d.jobs.find(j=>j.id===jobId)?.status),'inference');
  assert.equal(state.jobs.find(j=>j.id===jobId).status,'REVIEW_REQUIRED',JSON.stringify(state.jobs));
  state=await waitFor(d=>d.jobs.some(j=>j.payload.parent_job===jobId&&['REVIEW_REQUIRED','FAILED','BLOCKED'].includes(j.status)),'automatic Blender');
  assert.equal(state.jobs.find(j=>j.payload.parent_job===jobId).status,'REVIEW_REQUIRED');
  await page.getByRole('link',{name:'Library',exact:true}).click();
  await page.getByRole('button',{name:'Archer Tower T3 / UI acceptance',exact:true}).click();
  await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.getAttribute('data-loaded')||0)>0,null,{timeout:90000});
  await page.getByLabel('View camera').selectOption('back');
  await page.getByRole('button',{name:'Clay',exact:true}).click();
  await page.getByLabel('View camera').selectOption('bottom');
  await page.getByRole('button',{name:/^(PBR|Textured)$/}).click();
  await page.getByLabel('View camera').selectOption('three_quarter');
  state=await snapshot();
  if (state.assets.find(a=>a.id===assetId).status !== 'Approved') {
  await page.getByRole('button',{name:/^Approve master$/i}).click();
  await page.getByLabel('Reviewer',{exact:true}).fill('Automated UI acceptance / NOT production artist approval');
  await page.getByLabel('Review notes').fill('Exercise master version persistence only. Real generated output; no visual quality score and no Meshy or Unity acceptance.');
  await page.getByRole('button',{name:'Approve this master',exact:true}).click();
  }
  if (state.jobs.filter(j=>j.payload.kind==='blender').length<2) {
  await page.getByRole('button',{name:/Enhance in Blender|Improve/,exact:true}).click();
  }
  state=await waitFor(d=>d.jobs.filter(j=>j.payload.kind==='blender').length>=2&&d.jobs.filter(j=>j.payload.kind==='blender').every(j=>['REVIEW_REQUIRED','FAILED','BLOCKED'].includes(j.status)),'manual Blender');
  assert(state.jobs.filter(j=>j.payload.kind==='blender').every(j=>j.status==='REVIEW_REQUIRED'));
  await page.getByRole('button',{name:'Export',exact:true}).click();
  await page.getByRole('dialog').locator('select').nth(0).selectOption('Master');
  await page.getByRole('dialog').locator('select').nth(1).selectOption('glb');
  await page.getByRole('button',{name:'Prepare export',exact:true}).click();
  await page.getByRole('dialog').locator('.export-files a').first().waitFor();
  const url=await page.getByRole('dialog').locator('.export-files a').first().getAttribute('href');
  const download=await page.request.get(new URL(url,base).href); const bytes=await download.body();
  assert.equal(bytes.subarray(0,4).toString(),'glTF'); evidence.export_bytes=bytes.length;
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  const old=await snapshot();const oldAsset=old.assets.find(a=>a.id===assetId);
  assert.equal(oldAsset.status,'Approved'); assert(oldAsset.master_artifact_id); assert(oldAsset.versions.length>=2);
  await page.evaluate(()=>{const banner=document.createElement('div');banner.textContent='REAL PIPELINE ACCEPTANCE / QA DATABASE / NOT ARTIST OR MESHY APPROVAL';banner.style.cssText='position:fixed;top:0;left:0;right:0;background:#683d20;color:white;z-index:10000;padding:8px;text-align:center;font-size:12px';document.body.append(banner);});
  await page.screenshot({path:path.join(root,'docs/evidence/studio_acceptance_result.png'),fullPage:true});
  await context.close();
  context=await browser.newContext({viewport:{width:1600,height:1100}});page=await context.newPage();
  page.on('pageerror', e=>evidence.errors.push(String(e)));
  await page.goto(base+'/#library');
  await page.getByRole('button',{name:'Archer Tower T3 / UI acceptance',exact:true}).click();
  await page.waitForFunction(()=>Number(document.querySelector('.viewer')?.getAttribute('data-loaded')||0)>0,null,{timeout:90000});
  assert.equal(await page.getByLabel('Describe your asset').inputValue(),prompt);
  const reopened=(await snapshot()).assets.find(a=>a.id===assetId);
  assert.equal(reopened.master_artifact_id,oldAsset.master_artifact_id);
  assert.equal(reopened.versions.length,oldAsset.versions.length);
  evidence.asset={id:assetId,master:reopened.master_artifact_id,versions:reopened.versions.length,prompt_restored:true,exports:reopened.exports.length};
  evidence.inference_count_after_reopen=(await snapshot()).jobs.filter(j=>j.payload.kind==='inference').length;
  assert.equal(evidence.inference_count_after_reopen,1); assert.equal(evidence.errors.length,0);
  evidence.status='PASS';console.log('STUDIO_REAL_ACCEPTANCE_PASS',JSON.stringify(evidence.asset));
} catch(e) {evidence.status='FAILED';evidence.error=String(e); console.error(e);process.exitCode=1;}
finally {await fs.writeFile(path.join(root,'docs/evidence/studio_real_flow.json'),JSON.stringify(evidence,null,2));await browser.close();}
